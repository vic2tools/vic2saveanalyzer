"""State compositions preserve ownership, cultures, literacy and multiline regions."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finishing import state_population
from nation import trim_save
from mod_reader import province_regions
from readsave import PLAIN, analyze_save, reading_for
from readboth import both_ways, differences
from types import SimpleNamespace
import fastscan
import savefmt

regions = {1: 'shared', 2: 'shared', 3: 'shared', 4: 'colony'}
mod = SimpleNamespace(pop_types=(), reform_names=(), province_regions=regions)
reading = reading_for(None, mod, PLAIN.mob_types)
assert reading.fingerprint() != reading._replace(population_groups=()).fingerprint()
with tempfile.TemporaryDirectory() as tmp:
    path = str(Path(tmp) / 'states.v2')
    state = lambda ids, extra=(): ('state',
        savefmt.nest('provinces', ['\t\t\t' + ids], 2) + list(extra))
    parts = [savefmt.head('1880.1.1'),
             savefmt.province(1, 'ENG', [savefmt.pop('clerks', 1, 100, literacy=1)]),
             savefmt.province(2, 'ENG', [savefmt.pop('farmers', 2, 500, culture='irish', literacy=.1),
                                       savefmt.pop('farmers', 3, 400, culture='french', literacy=.1)]),
             savefmt.province(3, 'FRA', [savefmt.pop('farmers', 4, 500, culture='french', literacy=.8)]),
             savefmt.province(4, 'ENG', [savefmt.pop('farmers', 5, 200, culture='french', literacy=.2)]),
             savefmt.province(5, 'ENG', [savefmt.pop('soldiers', 6, 50, literacy=.5)]),
             savefmt.province(6, None, [savefmt.pop('farmers', 7, 111)]),
             savefmt.country('ENG', blocks=[('culture', ['\t\t"irish"']),
                 state('1'), state('2'), state('4', ['\t\tis_colonial=2']), state('5')]),
             savefmt.country('FRA', culture='french', blocks=[state('3')])]
    savefmt.write(path, *parts)
    if fastscan.available():
        fast, slow = both_ways(path, reading)
        assert not list(differences(fast, slow))
    else:
        slow = analyze_save(path, reading, use_scanner=False, verbose=False)
    meta, nations = slow
    a, b = nations['ENG'], nations['FRA']
    assert meta['world_pop'] == 1861   # Includes unowned land.
    assert a['pop_noncolonial'] == 1050
    assert a['literacy_noncolonial'] == 215
    assert a['soldiers_noncolonial'] == 50
    assert a['mob_excluded_culture'] == 600
    assert a['mobilizable_pops'] == [('farmers', 'irish', 500, 2)]
    assert len(a['population_by_state']) == 3  # Two save states share one region.
    # Country-first input order and nonstandard whitespace use the same path.
    savefmt.write(path, parts[0], *parts[-2:], *parts[1:-2])
    reordered = analyze_save(path, reading, use_scanner=False, verbose=False)
    assert reordered[1] == nations
    text = Path(path).read_text().replace('=\n{', '= {').replace('\t', '    ')
    Path(path).write_text(text)
    assert analyze_save(path, reading, use_scanner=False, verbose=False)[1] == nations
rows = state_population(a, regions)
assert rows['shared'] == [1000, .19, {'clerks': 100, 'farmers': 900}, [['british',100,True],['irish',500,True],['french',400,False]], 2]
assert rows['colony'][:2] == [200, .2]
assert rows['province:5'][:2] == [50, .5]
assert state_population(b, regions)['shared'][:2] == [500, .8]
assert sum(v[0] for v in rows.values()) == 1250
for row in rows.values():
    assert sum(row[2].values()) == row[0] == sum(c[1] for c in row[3])
zero = dict(a, population_by_state={1: [0, 0.0, {}, {}, 1]})
assert state_population(zero, regions)['shared'] == [0, None, {}, [], 1]
_, kept = trim_save({'date': '1880.1.1'}, {'AAA': {'population_states': rows}})
assert kept['AAA']['population_states'] == rows
from state_history import Snapshot, unpack, expand_map
snapshot = Snapshot()
snapshot.add('ENG', a['population_by_state'], regions, {'british', 'irish'})
snapshot.add('FRA', b['population_by_state'], regions, {'french'})
snapshot.add('ZER', zero['population_by_state'], regions, {'british'})
expected = {'ENG': rows, 'FRA': state_population(b, regions),
            'ZER': state_population(zero, regions)}
from readboth import normalise
assert normalise(unpack(snapshot.pack())) == normalise(expected)
assert snapshot.pack() == snapshot.pack()  # No wall-clock timestamp in chunks.
wire = {'populationStates': {}, 'populationStateChunks': [('1880.1.1', snapshot.pack())]}
assert expand_map(wire) == {'populationStates': {'1880.1.1': expected}}
# Regions are opaque names, including names that are special JS object keys.
odd_regions = dict(regions)
odd_regions[1] = '__proto__'
odd_regions[4] = '<colony>'
odd = Snapshot()
odd.add('ENG', a['population_by_state'], odd_regions, {'british'})
assert '__proto__' in unpack(odd.pack())['ENG']
assert '‹colony›' in unpack(odd.pack())['ENG']
with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp);(path/'map').mkdir()
    (path/'map/region.txt').write_text('BENGAL = { 1 2 }\nBIHAR = {\n3 4 # comment\n5\n}\nMETA = { 1 2 3 4 5 }')
    assert province_regions(tmp) == {1:'BENGAL',2:'BENGAL',3:'BIHAR',4:'BIHAR',5:'BIHAR'}
print('State details and multiline regions: PASS')
