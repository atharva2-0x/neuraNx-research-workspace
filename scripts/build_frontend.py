from pathlib import Path
import shutil
p=Path("public");p.mkdir(exist_ok=True)
shutil.copytree("ui",p/"static",dirs_exist_ok=True)
s=Path("ui/index.html").read_text().replace("Local, private workspace","Private browser workspace").replace("Local workspace","Private browser workspace").replace("Up to 25 MB","Up to 4 MB")
(p/"index.html").write_text(s)
a=p/"static/app.js";a.write_text(a.read_text().replace("25*1024*1024","4*1024*1024").replace("smaller than 25 MB","smaller than 4 MB"))
for f in Path("docs").glob("*.html"):shutil.copy2(f,p/f.name)
