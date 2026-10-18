"""Fresh-process restricted preload and full event evidence (BACK-2039)."""
import json
import os
import pickle
import subprocess
import sys
from pathlib import Path

import pytest

from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.scan_caches import get_scan_disclosures, preload_scan_caches
from test_i007_discovery_consumer_back2039 import Denial, check, project, write

pytestmark = pytest.mark.component

CHILD = r'''
import json, pickle, sys
from pathlib import Path
import reveal
from reveal.rules.imports import _dep_reconciliation as dep
from reveal.rules.imports.I007 import I007
from reveal.rules.scan_caches import init_scan_caches, get_scan_disclosures
checkout, manifest, other, first, second = pickle.loads(sys.stdin.buffer.read())
assert Path(reveal.__file__).resolve().is_relative_to(Path(checkout))
assert not dep._scan_cache
builds=[]
def unexpected(*args,**kwargs):
    builds.append(str(args[0]))
    raise RuntimeError('fresh initializer must reuse transferred native facts')
dep._scan_project_imports_uncached=unexpected
init_scan_caches(first)
init_scan_caches(second)
root=Path(manifest).parent
assert len(dep._scan_cache[root])==2
rule=I007();found=rule.check(manifest,None,'')
other_rule=I007();other_found=other_rule.check(other,None,'')
callback=[]
helper=dep.python_declared_unused if manifest.endswith('pyproject.toml') else dep.rust_declared_unused
result=helper(root,on_traversal_failure=callback.append)
print(json.dumps({'findings':[d.context for d in found], 'other_findings':[d.context for d in other_found],
 'outcomes':rule.outcomes,'other_outcomes':other_rule.outcomes,'notes':get_scan_disclosures([Path(manifest)],['I007'],None),
 'other_notes':get_scan_disclosures([Path(other)],['I007'],None),'builds':builds,'events':callback,'pair':list(result),
 'roots':[str(p) for p in dep._scan_cache]},default=lambda value:sorted(value)))
'''


@pytest.mark.parametrize('language', ['.py', '.rs'])
def test_real_fresh_process_merges_restricted_language_preloads_without_rescan(project, monkeypatch, language):
    manifest=project[language]
    other=project['.rs' if language=='.py' else '.py']
    fault=Denial(monkeypatch,manifest.parent,language,unknown=True)
    partial=preload_scan_caches([manifest],manifest.parent,['I007'],None)
    healthy=preload_scan_caches([other],manifest.parent,['I007'],None)
    assert fault.events and len(fault.builds)==2
    assert len(partial['I007'][manifest.parent])==len(healthy['I007'][manifest.parent])==1
    expected=get_scan_disclosures([manifest],['I007'],None)
    assert len(expected)==1
    checkout=str(Path(__file__).resolve().parents[1])
    packet=pickle.dumps((checkout,str(manifest),str(other),healthy,partial))
    completed=subprocess.run([sys.executable,'-c',CHILD],input=packet,capture_output=True,
                             env=dict(os.environ,PYTHONPATH=checkout),check=True)
    data=json.loads(completed.stdout.decode('utf-8'))
    assert len(data['findings'])==1 and data['other_findings']==[]
    assert data['builds']==[] and len(data['events'])==1 and data['events'][0][0] is None
    assert data['other_notes']==[] and data['other_outcomes']==[]
    assert data['notes']==expected and data['outcomes'][0]['reason']==expected[0]
    assert data['roots']==[str(manifest.parent)]


@pytest.mark.parametrize('unknown', [False, True])
def test_seven_real_enumeration_events_remain_complete_despite_display_limit(project, monkeypatch, unknown):
    manifest=project['.py'];root=manifest.parent
    denied={write(root/f'blocked{i}'/'usage.py','import requests\n').parent for i in range(7)}
    real_scan,real_scandir=dep._scan_project_imports_uncached,os.scandir
    state={'active':False,'events':[],'builds':0}
    def scan(*args,**kwargs):
        state['active']=True;state['builds']+=1
        try:return real_scan(*args,**kwargs)
        finally:state['active']=False
    def scandir(path):
        if state['active'] and Path(path) in denied:
            state['events'].append(str(path))
            if unknown:raise PermissionError('seven actual unnamed analytical directory events')
            raise PermissionError(13,'seven actual named analytical directory events',str(path))
        return real_scandir(path)
    monkeypatch.setattr(dep,'_scan_project_imports_uncached',scan)
    monkeypatch.setattr(os,'scandir',scandir)
    assert check(manifest)[0]==[]  # Uses also exist outside denied paths; zero findings is not completeness.
    assert len(state['events'])==7
    notes=get_scan_disclosures([manifest],['I007'],None)
    assert len(notes)==1 and str(root) in notes[0] and 'Python' in notes[0]
    facts=next(iter(dep._scan_cache[root].values()))
    assert len(facts.traversal_failures)==7
    callback=[]
    assert dep.python_declared_unused(root,on_traversal_failure=callback.append).unused==frozenset()
    assert tuple(callback)==facts.traversal_failures and state['builds']==1
    if unknown:
        assert all(path is None for path,_ in callback)
        assert '0 identified directory' in notes[0] and '7 enumeration error event(s)' in notes[0]
    else:
        assert {path for path,_ in callback}=={str(path) for path in denied}
        assert '7 identified directory enumeration(s)' in notes[0]
        # Formatter displays bounded examples while retaining all events for replay.
        assert 'and 2 more' in notes[0]
