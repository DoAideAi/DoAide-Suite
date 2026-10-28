"""Verify published native-service patches reconstruct the tested source files."""
import io,json,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
checks=[('inventory','DoAide-Inventory','2302fde10e218715ee880db6bf306a3191ac5e85'),('khata','DoAide-Khata','451333fdedb1350a45523492def4572d4e31a30d')]
results=[]
for folder,repo,base in checks:
    source=ROOT.parent/repo;head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    archive=subprocess.check_output(['git','archive',base],cwd=source)
    with tempfile.TemporaryDirectory(prefix='doaide-patch-check-') as temporary:
        target=Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as files:files.extractall(target,filter='data')
        patches=sorted((ROOT/'integrations'/folder).glob('*.patch'))
        for patch in patches:
            subprocess.run(['git','apply','--check',str(patch)],cwd=target,check=True)
            subprocess.run(['git','apply',str(patch)],cwd=target,check=True)
        changed=subprocess.check_output(['git','diff','--name-only',base,head],cwd=source,text=True).splitlines()
        for name in changed:assert (target/name).read_bytes()==(source/name).read_bytes(),name
        results.append({'service':folder,'base':base,'head':head,'patches':len(patches),'verified_files':len(changed)})
print(json.dumps(results,indent=2))
