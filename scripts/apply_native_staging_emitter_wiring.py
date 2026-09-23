#!/usr/bin/env python3
from pathlib import Path
import hashlib
p=Path('ProcessLib/Process.cpp')
raw=p.read_bytes()
blob=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
expected='0ef8df1243f3877c400b8c89005ab575d21b6c4d'
if blob != expected:
    raise SystemExit(f'FAIL_CLOSED: source blob {blob} != {expected}')
s=raw.decode('utf-8')
reps=[
('#include "ParameterLib/Parameter.h"\n#include "ProcessVariable.h"','#include "ParameterLib/Parameter.h"\n#include "NativeStagingEmitter.h"\n#include "ProcessVariable.h"'),
('    {\n        return;\n    }\n\n    // Some process variable has deactivated elements.','    {\n        emitNativeStagingState(name, time, process_id,\n                               _ids_of_active_elements,\n                               _mesh.getNumberOfElements());\n        return;\n    }\n\n    // Some process variable has deactivated elements.'),
('        _ids_of_active_elements = std::move(new_active_elements);\n    }\n}\n\nvoid Process::preAssemble','        _ids_of_active_elements = std::move(new_active_elements);\n    }\n\n    emitNativeStagingState(name, time, process_id, _ids_of_active_elements,\n                           _mesh.getNumberOfElements());\n}\n\nvoid Process::preAssemble')]
for old,new in reps:
    if s.count(old)!=1:
        raise SystemExit(f'FAIL_CLOSED: audited anchor count={s.count(old)}')
    s=s.replace(old,new,1)
if s.count('NativeStagingEmitter.h')!=1 or s.count('emitNativeStagingState(')!=2:
    raise SystemExit('FAIL_CLOSED: postcondition mismatch')
p.write_text(s,encoding='utf-8')
print('NATIVE_STAGING_WIRING_APPLIED=PASS')
