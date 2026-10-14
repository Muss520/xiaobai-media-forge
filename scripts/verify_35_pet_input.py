from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
"""Re-run the established native input contract against the 3.5 Xiaobai frames."""
import json,runpy
from pathlib import Path
root=Path(__file__).resolve().parents[1]
runpy.run_path(str(root/'scripts/verify_34_pet_input.py'),run_name='__main__')
result=json.loads((root/'docs/3.4_小白原生输入.json').read_text(encoding='utf-8'))
result['version']='3.5.0'
(root/'docs/3.5_小白原生输入.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
