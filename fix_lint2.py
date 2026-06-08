import pathlib

SRC = pathlib.Path("D:/sejong_major/projects/compliance-agent/frontend/src")

# Fix AgentTraceDrawer.jsx - remove unused eslint-disable for setError(null)
f = SRC / "components" / "AgentTraceDrawer.jsx"
content = f.read_text(encoding="utf-8")
content = content.replace(
    "    // eslint-disable-next-line react-hooks/set-state-in-effect\n    setError(null);",
    "    setError(null);"
)
f.write_text(content, encoding="utf-8")

# Fix CaseWorkspacePage.jsx - add eslint-disable for loadCase dependency
f = SRC / "pages" / "CaseWorkspacePage.jsx"
content = f.read_text(encoding="utf-8")
content = content.replace(
    "  // eslint-disable-next-line react-hooks/set-state-in-effect\n  useEffect(() => { loadCase(); }, [id]);",
    "  // eslint-disable-next-line react-hooks/exhaustive-deps,react-hooks/set-state-in-effect\n  useEffect(() => { loadCase(); }, [id]);"
)
f.write_text(content, encoding="utf-8")

print("Done.")
