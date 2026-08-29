from __future__ import annotations
import argparse
from pathlib import Path


def load_engine():
    source = Path('research/autonomous_search_v2.py').read_text()
    bad = 'ctx=contexts[(c["instrument"],c["timeframe"]);'
    good = 'ctx=contexts[(c["instrument"],c["timeframe"])];'
    if bad not in source:
        raise RuntimeError('expected audited source typo not found')
    source = source.replace(bad, good, 1)
    ns = {'__name__': 'autonomous_search_v2_engine', '__file__': 'research/autonomous_search_v2.py'}
    exec(compile(source, 'research/autonomous_search_v2.py', 'exec'), ns)

    original_execution_index = ns['execution_index']
    index_cache = {}
    def cached_execution_index(frame):
        key = id(frame)
        if key not in index_cache:
            index_cache[key] = original_execution_index(frame)
        return index_cache[key]
    ns['execution_index'] = cached_execution_index

    original_validation_states = ns['validation_states']
    state_cache = {}
    def cached_validation_states(signal_f, features, train_start, train_end):
        key = (id(signal_f), train_start, train_end)
        if key not in state_cache:
            state_cache[key] = original_validation_states(signal_f, features, train_start, train_end)
        return state_cache[key]
    ns['validation_states'] = cached_validation_states
    return ns


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    engine = load_engine()
    manifest = engine['run'](args.data_root, args.output)
    print(engine['json'].dumps(manifest, indent=2, default=engine['jsonable']))


if __name__ == '__main__':
    main()
