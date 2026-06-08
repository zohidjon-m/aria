import pathlib

SRC = pathlib.Path("D:/sejong_major/projects/compliance-agent/frontend/src")

f = SRC / "pages" / "CaseWorkspacePage.jsx"
content = f.read_text(encoding="utf-8")
# Only keep the exhaustive-deps disable, remove the set-state-in-effect one
content = content.replace(
    "  // eslint-disable-next-line react-hooks/exhaustive-deps,react-hooks/set-state-in-effect\n  useEffect(() => { loadCase(); }, [id]);",
    "  // eslint-disable-next-line react-hooks/exhaustive-deps\n  useEffect(() => { loadCase(); }, [id]);"
)
f.write_text(content, encoding="utf-8")
print("Done.")
