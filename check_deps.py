import importlib.util
for mod in ['matplotlib', 'networkx']:
    spec = importlib.util.find_spec(mod)
    if spec:
        m = __import__(mod)
        print(f'{mod}: {getattr(m, "__version__", "?")}')
    else:
        print(f'{mod}: NOT installed')
