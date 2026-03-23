"""
patch_skills.py — Option A: semantic skill retrieval (fixed)
Replaces keyword load_relevant_skills() with sentence-transformers cosine similarity.
Run once on Kiki, then delete.
"""

from pathlib import Path
import re, shutil, py_compile

SKILLS_PY = Path("/home/yanflare/kdev-deploy/skills.py")

NEW_CODE = (
    "# ══════════════════════════════════════════════════════════════════════════════\n"
    "#  Skill Index — semantic retrieval via sentence-transformers\n"
    "# ══════════════════════════════════════════════════════════════════════════════\n"
    "import numpy as np\n"
    "\n"
    "class SkillIndex:\n"
    '    """\n'
    "    Builds and caches a semantic embedding index over ~/.kdev/skills/*.md.\n"
    "    Rebuilt only when the skills directory mtime changes.\n"
    '    """\n'
    '    MODEL_NAME  = "all-MiniLM-L6-v2"\n'
    "    INDEX_NPY   = KDEV_DIR / \"skills.index.npy\"\n"
    "    INDEX_JSON  = KDEV_DIR / \"skills.index.json\"\n"
    "    MTIME_FILE  = KDEV_DIR / \"skills.index.mtime\"\n"
    "\n"
    "    def __init__(self):\n"
    "        self._model  = None\n"
    "        self._vecs   = None\n"
    "        self._meta   = []\n"
    "        self._mtime  = None\n"
    "        self._load_or_build()\n"
    "\n"
    "    def _get_model(self):\n"
    "        if self._model is None:\n"
    "            from sentence_transformers import SentenceTransformer\n"
    "            self._model = SentenceTransformer(self.MODEL_NAME)\n"
    "        return self._model\n"
    "\n"
    "    def _skills_mtime(self) -> float:\n"
    "        try:\n"
    "            return SKILLS_DIR.stat().st_mtime\n"
    "        except Exception:\n"
    "            return 0.0\n"
    "\n"
    "    def _cached_mtime(self) -> float:\n"
    "        try:\n"
    "            return float(self.MTIME_FILE.read_text().strip())\n"
    "        except Exception:\n"
    "            return -1.0\n"
    "\n"
    "    def _build(self):\n"
    "        import json as _json\n"
    "        skill_files = sorted(SKILLS_DIR.rglob(\"*.md\"), reverse=True)\n"
    "        if not skill_files:\n"
    "            self._vecs = np.zeros((0, 384), dtype=np.float32)\n"
    "            self._meta = []\n"
    "            return\n"
    "        texts = []\n"
    "        meta  = []\n"
    "        for sf in skill_files:\n"
    "            try:\n"
    "                text = sf.read_text(encoding=\"utf-8\")\n"
    "            except Exception:\n"
    "                continue\n"
    "            title_m   = re.search(r\"title:\\s*(.+)\", text) or re.search(r\"name:\\s*(.+)\", text)\n"
    "            tags_m    = re.search(r\"tags:\\s*(.+)\", text)\n"
    "            summary_m = re.search(r\"summary:\\s*(.+)\", text) or re.search(r\"description:\\s*(.+)\", text)\n"
    "            label   = title_m.group(1).strip()   if title_m   else sf.stem\n"
    "            summary = summary_m.group(1).strip() if summary_m else \"\"\n"
    "            tags    = tags_m.group(1).strip()    if tags_m    else \"\"\n"
    "            embed_text = \" \".join(filter(None, [label, tags, summary]))\n"
    "            texts.append(embed_text)\n"
    "            meta.append({\"path\": str(sf), \"text\": text, \"label\": label, \"summary\": summary})\n"
    "        if not texts:\n"
    "            self._vecs = np.zeros((0, 384), dtype=np.float32)\n"
    "            self._meta = []\n"
    "            return\n"
    "        model = self._get_model()\n"
    "        vecs  = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)\n"
    "        self._vecs = vecs.astype(np.float32)\n"
    "        self._meta = meta\n"
    "        np.save(str(self.INDEX_NPY), self._vecs)\n"
    "        self.INDEX_JSON.write_text(_json.dumps(self._meta, ensure_ascii=False), encoding=\"utf-8\")\n"
    "        self.MTIME_FILE.write_text(str(self._skills_mtime()))\n"
    "\n"
    "    def _load_or_build(self):\n"
    "        import json as _json\n"
    "        current_mtime = self._skills_mtime()\n"
    "        if (self.INDEX_NPY.exists()\n"
    "                and self.INDEX_JSON.exists()\n"
    "                and self._cached_mtime() == current_mtime):\n"
    "            try:\n"
    "                self._vecs = np.load(str(self.INDEX_NPY))\n"
    "                self._meta = _json.loads(self.INDEX_JSON.read_text(encoding=\"utf-8\"))\n"
    "                self._mtime = current_mtime\n"
    "                return\n"
    "            except Exception:\n"
    "                pass\n"
    "        self._build()\n"
    "        self._mtime = current_mtime\n"
    "\n"
    "    def refresh_if_stale(self):\n"
    "        current_mtime = self._skills_mtime()\n"
    "        if current_mtime != self._mtime:\n"
    "            self._build()\n"
    "            self._mtime = current_mtime\n"
    "\n"
    "    def top_k(self, query: str, k: int = 3) -> list:\n"
    '        """Return top-k skill metadata dicts sorted by cosine similarity."""\n'
    "        self.refresh_if_stale()\n"
    "        if self._vecs is None or len(self._vecs) == 0:\n"
    "            return []\n"
    "        model  = self._get_model()\n"
    "        q_vec  = model.encode([query], normalize_embeddings=True,\n"
    "                               show_progress_bar=False)[0].astype(np.float32)\n"
    "        scores = self._vecs @ q_vec\n"
    "        idx    = np.argsort(scores)[::-1][:k]\n"
    "        return [dict(score=float(scores[i]), **self._meta[i]) for i in idx]\n"
    "\n"
    "\n"
    "_skill_index = None\n"
    "\n"
    "def _get_skill_index():\n"
    "    global _skill_index\n"
    "    if _skill_index is None:\n"
    "        _skill_index = SkillIndex()\n"
    "    return _skill_index\n"
    "\n"
    "\n"
    "# ══════════════════════════════════════════════════════════════════════════════\n"
    "#  Skill Loading — semantic retrieval (replaces keyword matcher)\n"
    "# ══════════════════════════════════════════════════════════════════════════════\n"
    "def load_relevant_skills(task: str, max_skills: int = 3) -> str:\n"
    '    """\n'
    "    Semantic search over skill docs using sentence-transformers cosine similarity.\n"
    "    Returns a formatted string to append to the system prompt.\n"
    '    """\n'
    "    if not SKILLS_DIR.exists():\n"
    "        return \"\"\n"
    "    try:\n"
    "        index   = _get_skill_index()\n"
    "        results = index.top_k(task, k=max_skills)\n"
    "    except Exception:\n"
    "        return \"\"\n"
    "    if not results:\n"
    "        return \"\"\n"
    "    parts = [\"## Relevant skills from previous sessions\\n\"]\n"
    "    for r in results:\n"
    "        text    = r[\"text\"]\n"
    "        label   = r[\"label\"]\n"
    "        summary = r[\"summary\"]\n"
    "        body    = re.sub(r\"^---.*?---\\s*\", \"\", text, flags=re.DOTALL).strip()\n"
    "        parts.append(f\"### {label}\")\n"
    "        if summary:\n"
    "            parts.append(f\"*{summary}*\\n\")\n"
    "        parts.append(body[:600])\n"
    "        parts.append(\"\")\n"
    "    return \"\\n\".join(parts)\n"
)


def patch():
    src = SKILLS_PY.read_text(encoding="utf-8")

    # Find start of old Skill Loading section
    start_marker = "# ══════════════════════════════════════════════════════════════════════════════\n#  Skill Loading — inject relevant skills into system prompt"
    end_marker   = "\ndef list_skills"

    start = src.find(start_marker)
    end   = src.find(end_marker, start)

    if start == -1 or end == -1:
        print("ERROR: Could not locate 'Skill Loading' section — aborting.")
        return

    # Backup
    bak = SKILLS_PY.with_suffix(".py.bak_optionA")
    bak.write_text(src, encoding="utf-8")
    print(f"Backup written: {bak}")

    # Splice
    new_src = src[:start] + NEW_CODE + src[end:]
    SKILLS_PY.write_text(new_src, encoding="utf-8")
    print("Patch applied: skills.py updated.")

    # Verify compile
    try:
        py_compile.compile(str(SKILLS_PY), doraise=True)
        print("py_compile: OK")
    except py_compile.PyCompileError as e:
        print(f"COMPILE ERROR — restoring backup: {e}")
        shutil.copy(str(bak), str(SKILLS_PY))
        print("Backup restored.")


if __name__ == "__main__":
    patch()
