from sacred import Experiment
from sacred.utils import apply_backspaces_and_linefeeds
from experiments.utils import get_mongo_observer
from experiments.evaluation import evaluate, import_weights_into_network
from experiments.different_evaluation_parameters import parameter_combinations
from xview.datasets import get_dataset
from xview.models import DirichletMix


ex = Experiment()
# reduce output of progress bars
ex.captured_out_filter = apply_backspaces_and_linefeeds
ex.observers.append(get_mongo_observer())


@ex.command
def test_parameters(net_config, evaluation_data, starting_weights, search_paramters,
                    _run):
    # get the different configs we will test
    configs_to_test = parameter_combinations(search_paramters, net_config)

    # generate sufficient statistic
    some_config = configs_to_test[0]

    dataset_params = {key: val for key, val in evaluation_data.items()
                      if key not in ['dataset', 'use_trainset']}
    dataset_params['batchsize'] = 1
    # Load the dataset, we expect config to include the arguments
    data = get_dataset(evaluation_data['dataset'], dataset_params)
    batches = data.get_train_data(batch_size=6)
    with DirichletMix(**some_config) as net:
        import_weights_into_network(net, starting_weights)
        sufficient_statistic = net._get_sufficient_statistic(batches)

    data = load_data(evaluation_data)
    validation_data = data.get_validation_data()

    # Not test all the parameters
    results = []
    for test_parameters in configs_to_test:
        with DirichletMix(**test_parameters) as net:
            net._get_sufficient_statistic(*sufficient_statistic)
            import_weights_into_network(net, starting_weights)
            measurements, _ = net.fit(validation_data())

            # put results and parameters all in one dict
            result = {}
            result.update(test_parameters)
            result.update(measurements)
            results.append(result)

    # Results is not a list of dictionaries where all keys match. For convenience (e.g.
    # to impor the measurements into a pandas DataFrame, we convert it into a dict of
    # lists), see:
    # [https://stackoverflow.com/questions/5558418/list-of-dicts-to-from-dict-of-lists]
    _run.info['results'] = dict(zip(results[0], zip(*[r.values() for r in results])))


@ex.automain
def fit_and_evaluate(net_config, evaluation_data, starting_weights, _run):
    """Load weigths from trainign experiments and evalaute network against specified
    data."""
    with DirichletMix(**net_config) as net:
        import_weights_into_network(net, starting_weights)

        # Measure the single experts against the trainingset.
        dataset_params = {key: val for key, val in evaluation_data.items()
                          if key not in ['dataset', 'use_trainset']}
        dataset_params['batchsize'] = 1
        # Load the dataset, we expect config to include the arguments
        data = get_dataset(evaluation_data['dataset'], dataset_params)
        if evaluation_data['use_trainset']:
            dirichlet_params = net.fit(data.get_train_data(training_format=False))
        else:
            dirichlet_params = net.fit(data.get_validation_data()())

        # import weights again has fitting created new graph
        import_weights_into_network(net, starting_weights)

        # never evaluate against train data
        evaluation_data['use_trainset'] = False
        measurements, confusion_matrix = evaluate(net, evaluation_data)
        _run.info['measurements'] = measurements
        _run.info['confusion_matrix'] = confusion_matrix
        _run.info['dirichlet_params'] = dirichlet_params