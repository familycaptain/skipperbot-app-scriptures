import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import {
  BookOpen, Search, Bookmark, ChevronLeft, ChevronRight, ChevronDown,
  Loader2, Plus, Trash2, X, Type, RefreshCw,
} from "lucide-react";

/**
 * Scriptures App — Bible reading, search, and bookmarks
 *
 * Props: appId, userId, context, onTitle, onOpenApp, refreshKey
 */

const API = "/api/apps/scriptures";

// ─── Font sizes for TV-optimized reading ────────────────────────────────────
const FONT_SIZES = {
  large:  { verse: "text-2xl",  heading: "text-3xl",  verseNum: "text-base", summary: "text-2xl",  label: "Large" },
  xl:     { verse: "text-3xl",  heading: "text-4xl",  verseNum: "text-lg",   summary: "text-3xl", label: "XL" },
  huge:   { verse: "text-4xl",  heading: "text-5xl",  verseNum: "text-xl",   summary: "text-4xl", label: "Huge" },
};

const BOOKMARK_COLORS = ["blue", "green", "purple", "orange", "pink", "yellow"];
const COLOR_MAP = {
  blue: "bg-blue-600", green: "bg-green-600", purple: "bg-purple-600",
  orange: "bg-orange-600", pink: "bg-pink-500", yellow: "bg-yellow-500",
};
const COLOR_RING = {
  blue: "ring-blue-400", green: "ring-green-400", purple: "ring-purple-400",
  orange: "ring-orange-400", pink: "ring-pink-400", yellow: "ring-yellow-400",
};

// ─── Shared styles ──────────────────────────────────────────────────────────
const btnPrimary = "inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded bg-teal-600 hover:bg-teal-500 text-white disabled:opacity-50";
const btnSecondary = "px-3 py-1.5 text-sm rounded bg-gray-700 text-gray-300 hover:bg-gray-600";
const inp = "w-full text-sm bg-gray-900 border border-gray-600 rounded px-2 py-1.5 text-gray-200 focus:outline-none focus:border-teal-500";

const TABS = [
  { id: "read",      label: "Read",      Icon: BookOpen },
  { id: "search",    label: "Search",    Icon: Search },
  { id: "bookmarks", label: "Bookmarks", Icon: Bookmark },
];

// ═════════════════════════════════════════════════════════════════════════════
//  Main App
// ═════════════════════════════════════════════════════════════════════════════

export default function ScripturesApp({ appId, userId, onTitle, refreshKey }) {
  const [tab, setTab] = useState("read");
  const [fontSize, setFontSize] = useState(() => localStorage.getItem("scriptures_fontsize") || "xl");

  // Bible data
  const [versions, setVersions] = useState([]);
  const [versionId, setVersionId] = useState(() => localStorage.getItem("scriptures_version") || "");
  const [books, setBooks] = useState([]);
  const [book, setBook] = useState(1);
  const [chapter, setChapter] = useState(1);

  // Chapter data
  const [verses, setVerses] = useState([]);
  const [bookInfo, setBookInfo] = useState(null);
  const [chapterCount, setChapterCount] = useState(0);
  const [loading, setLoading] = useState(false);

  // LLM content tabs
  const [viewMode, setViewMode] = useState("scripture"); // "scripture" | "summary" | "people" | "places"
  const [summary, setSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [people, setPeople] = useState(null);
  const [peopleLoading, setPeopleLoading] = useState(false);
  const [places, setPlaces] = useState(null);
  const [placesLoading, setPlacesLoading] = useState(false);
  const [pronouns, setPronouns] = useState(null);
  const [pronounsLoading, setPronounsLoading] = useState(false);
  const [revealedPronouns, setRevealedPronouns] = useState({});

  // Bookmarks
  const [bookmarks, setBookmarks] = useState([]);

  // Book picker
  const [showBookPicker, setShowBookPicker] = useState(false);

  // Entity popup — lifted to root so EntityModal renders outside any stacking context
  const [selectedEntity, setSelectedEntity] = useState(null);
  const allEntities = useMemo(
    () => [...parseEntities(people, "person"), ...parseEntities(places, "place")],
    [people, places]
  );
  useEffect(() => {
    setSelectedEntity(null);
    setRevealedPronouns({});
  }, [book, chapter]);

  useEffect(() => { if (onTitle) onTitle("Scriptures"); }, [onTitle]);

  // Persist font size
  useEffect(() => { localStorage.setItem("scriptures_fontsize", fontSize); }, [fontSize]);

  // Load versions on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`${API}/versions`);
        const data = await res.json();
        setVersions(data.versions || []);
        if (!versionId && data.versions?.length) {
          const ts = data.versions.find(v => v.abbreviation === "TS2009");
          setVersionId(ts ? ts.id : data.versions[0].id);
        }
      } catch (e) { console.error("Failed to load versions", e); }
    })();
  }, [refreshKey]);

  // Load books when version changes
  useEffect(() => {
    if (!versionId) return;
    localStorage.setItem("scriptures_version", versionId);
    (async () => {
      try {
        const res = await fetch(`${API}/books?version_id=${versionId}`);
        const data = await res.json();
        setBooks(data.books || []);
      } catch (e) { console.error("Failed to load books", e); }
    })();
  }, [versionId]);

  // Load chapter when book/chapter/version changes
  const loadChapter = useCallback(async () => {
    if (!versionId) return;
    setLoading(true);
    setSummary(null);
    setPeople(null);
    setPlaces(null);
    setPronouns(null);
    setRevealedPronouns({});
    setViewMode("scripture");
    try {
      const res = await fetch(`${API}/read?version_id=${versionId}&book=${book}&chapter=${chapter}`);
      const data = await res.json();
      setVerses(data.verses || []);
      setBookInfo(data.book_info || null);
      setChapterCount(data.chapter_count || 0);
      setBookmarks(data.bookmarks || []);
      if (data.summary) setSummary(data.summary);
      if (data.people) setPeople(data.people);
      if (data.places) setPlaces(data.places);
      setPronouns(data.pronouns ?? null);
    } catch (e) { console.error("Failed to load chapter", e); }
    setLoading(false);
  }, [versionId, book, chapter]);

  useEffect(() => { loadChapter(); }, [loadChapter]);

  // Switch to summary → load if needed
  const handleViewSummary = async (force) => {
    setViewMode("summary");
    if (!force && summary) return;
    setSummaryLoading(true);
    try {
      const res = await fetch(`${API}/summary`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId, book, chapter }),
      });
      const data = await res.json();
      setSummary(data.summary);
    } catch (e) { console.error("Failed to generate summary", e); }
    setSummaryLoading(false);
  };

  const handleViewPeople = async (force) => {
    setViewMode("people");
    if (!force && people) return;
    setPeopleLoading(true);
    try {
      const res = await fetch(`${API}/people`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId, book, chapter }),
      });
      const data = await res.json();
      setPeople(data.people);
    } catch (e) { console.error("Failed to generate people", e); }
    setPeopleLoading(false);
  };

  const handleViewPlaces = async (force) => {
    setViewMode("places");
    if (!force && places) return;
    setPlacesLoading(true);
    try {
      const res = await fetch(`${API}/places`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId, book, chapter }),
      });
      const data = await res.json();
      setPlaces(data.places);
    } catch (e) { console.error("Failed to generate places", e); }
    setPlacesLoading(false);
  };

  const handleGeneratePronouns = async (force) => {
    if (!force && pronouns !== null) return;
    setPronounsLoading(true);
    try {
      const res = await fetch(`${API}/pronouns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId, book, chapter }),
      });
      const data = await res.json();
      setPronouns(data.pronouns ?? []);
      setRevealedPronouns({});
    } catch (e) { console.error("Failed to generate pronouns", e); }
    setPronounsLoading(false);
  };

  const handleRegenerate = async (field) => {
    try {
      await fetch(`${API}/regenerate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version_id: versionId, book, chapter, field }),
      });
      if (field === "summary") { setSummary(null); handleViewSummary(true); }
      else if (field === "people") { setPeople(null); handleViewPeople(true); }
      else if (field === "places") { setPlaces(null); handleViewPlaces(true); }
      else if (field === "pronouns") { setPronouns(null); setRevealedPronouns({}); handleGeneratePronouns(true); }
    } catch (e) { console.error("Failed to regenerate", e); }
  };

  // Navigation
  const goNext = () => {
    if (chapter < chapterCount) setChapter(c => c + 1);
    else if (book < 66) { setBook(b => b + 1); setChapter(1); }
  };
  const goPrev = () => {
    if (chapter > 1) setChapter(c => c - 1);
    else if (book > 1) {
      const prevBook = books.find(b => b.book_number === book - 1);
      setBook(b => b - 1);
      setChapter(prevBook?.chapter_count || 1);
    }
  };

  // Bookmark actions
  const moveBookmark = async (bmId) => {
    try {
      await fetch(`${API}/bookmarks/${bmId}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ book, chapter, user_id: userId || "" }),
      });
      loadChapter();
    } catch (e) { console.error("Failed to move bookmark", e); }
  };

  const goToBookmark = (bm) => {
    if (bm.version_id !== versionId) setVersionId(bm.version_id);
    setBook(bm.book);
    setChapter(bm.chapter);
    setTab("read");
  };

  const fs = FONT_SIZES[fontSize] || FONT_SIZES.xl;
  const bookName = bookInfo ? `${bookInfo.name} (${bookInfo.name_english})` : `Book ${book}`;

  return (
    <div className="flex flex-col h-full w-full bg-gray-900 text-gray-200">
      {/* Tab bar */}
      <div className="flex items-center border-b border-gray-700 bg-gray-850 px-2 shrink-0">
        {TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              tab === t.id ? "border-teal-400 text-teal-300" : "border-transparent text-gray-400 hover:text-gray-200"
            }`}>
            <t.Icon size={16} /> {t.label}
          </button>
        ))}

        {/* Font size toggle — right aligned */}
        <div className="ml-auto flex items-center gap-1 mr-1">
          <Type size={14} className="text-gray-500" />
          {Object.entries(FONT_SIZES).map(([key, val]) => (
            <button key={key} onClick={() => setFontSize(key)}
              className={`px-2 py-1 text-xs rounded ${
                fontSize === key ? "bg-teal-600 text-white" : "bg-gray-700 text-gray-400 hover:bg-gray-600"
              }`}>
              {val.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === "read" && (
          <ReadTab
            {...{ versionId, versions, setVersionId, books, book, setBook, chapter, setChapter,
                  verses, bookInfo, chapterCount, loading, viewMode, setViewMode,
                  summary, summaryLoading, handleViewSummary,
                  people, peopleLoading, handleViewPeople,
                  places, placesLoading, handleViewPlaces,
                  pronouns, pronounsLoading, handleGeneratePronouns, revealedPronouns, setRevealedPronouns,
                  handleRegenerate, bookmarks, bookName,
                  goNext, goPrev, moveBookmark, goToBookmark, fs,
                  showBookPicker, setShowBookPicker, userId,
                  allEntities, setSelectedEntity }}
          />
        )}
        {tab === "search" && <SearchTab versionId={versionId} goToVerse={(b, c) => { setBook(b); setChapter(c); setTab("read"); }} fs={fs} />}
        {tab === "bookmarks" && <BookmarksTab versionId={versionId} userId={userId} goToBookmark={goToBookmark} />}
      </div>

    {selectedEntity && (
      <EntityModal entityName={selectedEntity} allEntities={allEntities}
        onClose={() => setSelectedEntity(null)} fs={fs} />
    )}
  </div>
);
}


// ═════════════════════════════════════════════════════════════════════════════
//  Read Tab
// ═════════════════════════════════════════════════════════════════════════════

function ReadTab({
  versionId, versions, setVersionId, books, book, setBook, chapter, setChapter,
  verses, bookInfo, chapterCount, loading, viewMode, setViewMode,
  summary, summaryLoading, handleViewSummary,
  people, peopleLoading, handleViewPeople,
  places, placesLoading, handleViewPlaces,
  pronouns, pronounsLoading, handleGeneratePronouns, revealedPronouns, setRevealedPronouns,
  handleRegenerate, bookmarks, bookName,
  goNext, goPrev, moveBookmark, goToBookmark, fs,
  showBookPicker, setShowBookPicker, userId,
  allEntities, setSelectedEntity,
}) {
  const contentRef = useRef(null);
  const pronounsByVerse = useMemo(() => buildPronounVerseMap(pronouns), [pronouns]);

  // Scroll to top when chapter changes
  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [book, chapter]);


  return (
    <div className="flex flex-col h-full" ref={contentRef}>
      {/* Nav bar: version, book, chapter */}
      <div className="flex items-center gap-2 p-3 bg-gray-800 border-b border-gray-700 flex-wrap shrink-0 relative z-10">
        {versions.length > 1 && (
          <select value={versionId} onChange={e => setVersionId(e.target.value)}
            className="text-base bg-gray-900 border border-gray-600 rounded px-3 py-2 text-gray-200">
            {versions.map(v => <option key={v.id} value={v.id}>{v.abbreviation}</option>)}
          </select>
        )}

        <button onClick={() => setShowBookPicker(p => !p)}
          className="text-base bg-gray-700 hover:bg-gray-600 rounded px-3 py-2 text-gray-200 font-medium">
          {bookName}
        </button>

        <div className="flex items-center gap-1">
          <span className="text-xs text-gray-500">Ch</span>
          <select value={chapter} onChange={e => setChapter(Number(e.target.value))}
            className="text-base bg-gray-900 border border-gray-600 rounded px-3 py-2 text-gray-200">
            {Array.from({ length: chapterCount || 1 }, (_, i) => (
              <option key={i + 1} value={i + 1}>{i + 1}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Book picker modal */}
      {showBookPicker && (
        <BookPicker books={books} currentBook={book}
          onSelect={(num) => { setBook(num); setChapter(1); setShowBookPicker(false); }}
          onClose={() => setShowBookPicker(false)} />
      )}

      {/* Bookmarks bar */}
      {bookmarks.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-2 bg-gray-800/50 border-b border-gray-700 overflow-x-auto shrink-0">
          {bookmarks.map(bm => {
            const isHere = bm.book === book && bm.chapter === chapter;
            const color = bm.color || "blue";
            return (
              <div key={bm.id} className="flex items-center gap-1 shrink-0">
                <button onClick={() => goToBookmark(bm)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    isHere
                      ? `${COLOR_MAP[color]} text-white border-transparent ring-2 ${COLOR_RING[color]}`
                      : `bg-gray-700 text-gray-300 border-gray-600 hover:bg-gray-600`
                  }`}>
                  <Bookmark size={14} />
                  <span className="font-medium">{bm.name}</span>
                  <span className="text-xs opacity-70">
                    {bm.book_name || ""} {bm.chapter}
                  </span>
                </button>
                {!isHere && (
                  <button onClick={() => moveBookmark(bm.id)} title="Save current position to this bookmark"
                    className="text-xs text-gray-500 hover:text-teal-400 px-1">
                    ↓ Save
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Scripture / Summary / People / Places toggle */}
      <div className="flex items-center gap-1 px-3 py-2 shrink-0 flex-wrap">
        {[
          { key: "scripture", label: "Scripture", handler: () => setViewMode("scripture") },
          { key: "summary",   label: "Summary",   handler: () => { if (viewMode !== "summary") handleViewSummary(); else setViewMode("summary"); } },
          { key: "people",    label: "People",     handler: () => { if (viewMode !== "people") handleViewPeople(); else setViewMode("people"); } },
          { key: "places",    label: "Places",     handler: () => { if (viewMode !== "places") handleViewPlaces(); else setViewMode("places"); } },
        ].map((btn, idx, arr) => (
          <button key={btn.key} onClick={btn.handler}
            className={`px-4 py-1.5 text-sm font-medium border ${
              idx === 0 ? "rounded-l-lg" : idx === arr.length - 1 ? "rounded-r-lg" : ""
            } ${
              viewMode === btn.key
                ? "bg-teal-600 text-white border-teal-600"
                : "bg-gray-700 text-gray-300 border-gray-600 hover:bg-gray-600"
            }`}>
            {btn.label}
          </button>
        ))}

        {viewMode !== "scripture" && (
          <button onClick={() => handleRegenerate(viewMode)}
            title="Regenerate"
            className="ml-2 p-1.5 text-gray-400 hover:text-teal-400 hover:bg-gray-700 rounded transition-colors">
            <RefreshCw size={16} />
          </button>
        )}

        {viewMode === "scripture" && (
          <button
            onClick={() => (pronouns !== null ? handleRegenerate("pronouns") : handleGeneratePronouns())}
            disabled={pronounsLoading}
            className="ml-2 inline-flex items-center gap-2 px-3 py-1.5 text-sm rounded bg-violet-700 text-violet-100 hover:bg-violet-600 disabled:opacity-60"
          >
            {pronounsLoading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
            {pronouns !== null ? "Refresh Pronouns" : "Analyze Pronouns"}
          </button>
        )}
      </div>

      {/* Chapter heading */}
      <div className="px-4 pt-2 pb-0 mb-6">
        <h2 className={`${fs.heading} font-bold text-white`}>{bookName} {chapter}</h2>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-y-auto px-4 pb-8">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="animate-spin text-gray-500" size={32} />
          </div>
        ) : viewMode === "scripture" ? (
          <div className="leading-relaxed">
            {pronounsLoading && (
              <div className="mb-5 flex items-center gap-2 text-violet-300">
                <Loader2 size={18} className="animate-spin" />
                <span className="text-sm">Resolving pronouns…</span>
              </div>
            )}
            {verses.map(v => (
              <div key={v.verse} className="mb-6">
                <sup className={`${fs.verseNum} text-teal-500 font-semibold mr-1 select-none`}>
                  {v.verse}
                </sup>
                <VerseText
                  className={`${fs.verse} text-gray-100`}
                  html={v.text_html}
                  allEntities={allEntities}
                  pronounInstances={pronounsByVerse.get(v.verse) || []}
                  revealedPronouns={revealedPronouns}
                  onPronounReveal={(key) => setRevealedPronouns(prev => (prev[key] ? prev : { ...prev, [key]: true }))}
                  onEntityClick={setSelectedEntity}
                />
              </div>
            ))}
          </div>
        ) : viewMode === "summary" ? (
          <LlmContent content={summary} isLoading={summaryLoading} loadingLabel="Summarizing chapter…" emptyLabel="No summary available." fs={fs} allEntities={allEntities} onEntityClick={setSelectedEntity} />
        ) : viewMode === "people" ? (
          <LlmContent content={people} isLoading={peopleLoading} loadingLabel="Identifying people…" emptyLabel="No people data available." fs={fs} collapsible />
        ) : viewMode === "places" ? (
          <LlmContent content={places} isLoading={placesLoading} loadingLabel="Identifying places…" emptyLabel="No places data available." fs={fs} collapsible />
        ) : null}
      </div>

      {/* Prev / Next navigation */}
      <div className="flex items-center justify-between px-4 py-3 border-t border-gray-700 bg-gray-800 shrink-0">
        <button onClick={goPrev} disabled={book === 1 && chapter === 1}
          className="flex items-center gap-2 px-5 py-3 text-lg rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-30 transition-colors">
          <ChevronLeft size={24} /> Previous
        </button>
        <span className="text-sm text-gray-500">{chapter} / {chapterCount}</span>
        <button onClick={goNext} disabled={book === 66 && chapter === chapterCount}
          className="flex items-center gap-2 px-5 py-3 text-lg rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-200 disabled:opacity-30 transition-colors">
          Next <ChevronRight size={24} />
        </button>
      </div>

    </div>
  );
}


// ─── Entity helpers ────────────────────────────────────────────────────────

const ENTITY_TEXT_BOUNDARY = "[\\p{L}\\p{N}\\p{M}]";
const ENTITY_HEADER_RE = /^(?:[-*•]|\d+\.)?\s*\*\*(.+?)\*\*(.*)$/u;
const ENTITY_ALIAS_STOPWORDS = new Set([
  "a",
  "an",
  "the",
]);
const ENTITY_LINK_COLORS = {
  person: "#fbbf24",
  place: "#5eead4",
  pronoun: "#c084fc",
};
const ENTITY_SHORT_NAME_PATTERNS = [
  /\s+son of\b.*$/iu,
  /\s+daughter of\b.*$/iu,
  /\s+the prophet\b.*$/iu,
  /\s+the seer\b.*$/iu,
  /\s+the priest\b.*$/iu,
  /\s+the high priest\b.*$/iu,
  /\s+sovereign of\b.*$/iu,
  /\s+king of\b.*$/iu,
  /\s+queen of\b.*$/iu,
  /\s+governor of\b.*$/iu,
];

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function normalizeEntityName(value) {
  return (value || "").trim().replace(/\s+/g, " ");
}

function getEntityLinkStyle(entityType) {
  return {
    color: ENTITY_LINK_COLORS[entityType] || ENTITY_LINK_COLORS.place,
    textDecoration: "underline",
    textDecorationStyle: "dotted",
    cursor: "pointer",
  };
}

function getPronounReplacementStyle() {
  return {
    color: "#e9d5ff",
    fontWeight: 600,
  };
}

function isUsableEntityAlias(value) {
  const normalized = normalizeEntityName(value);
  if (!normalized) return false;
  if (ENTITY_ALIAS_STOPWORDS.has(normalized.toLocaleLowerCase())) return false;
  return /[\p{L}\p{N}]/u.test(normalized);
}

function getEntityAliases(name) {
  const normalized = normalizeEntityName(name);
  const aliases = new Set();
  if (!isUsableEntityAlias(normalized)) return [];
  aliases.add(normalized);
  for (const pattern of ENTITY_SHORT_NAME_PATTERNS) {
    const shortName = normalizeEntityName(normalized.replace(pattern, ""));
    if (shortName && shortName !== normalized && isUsableEntityAlias(shortName)) {
      aliases.add(shortName);
    }
  }
  return [...aliases];
}

function buildEntityMatcher(entities) {
  if (!entities?.length) return null;
  const entityByTerm = new Map();
  const terms = [];
  for (const entity of entities) {
    const canonicalName = normalizeEntityName(entity.name);
    const aliases = entity.aliases?.length ? entity.aliases : getEntityAliases(canonicalName);
    for (const alias of aliases) {
      const term = normalizeEntityName(alias);
      const key = term.toLocaleLowerCase();
      if (!term || entityByTerm.has(key)) continue;
      entityByTerm.set(key, { ...entity, name: canonicalName });
      terms.push(term);
    }
  }
  if (!terms.length) return null;
  terms.sort((a, b) => b.length - a.length);
  const combined = terms.map(escapeRegExp).join("|");
  return {
    entityByTerm,
    regex: new RegExp(`(?<!${ENTITY_TEXT_BOUNDARY})(${combined})(?!${ENTITY_TEXT_BOUNDARY})`, "giu"),
  };
}

function buildPronounVerseMap(pronouns) {
  const byVerse = new Map();
  if (!Array.isArray(pronouns)) return byVerse;
  for (const verseEntry of pronouns) {
    const verseNum = Number(verseEntry?.verse);
    const rawInstances = Array.isArray(verseEntry?.instances) ? verseEntry.instances : [];
    if (!Number.isFinite(verseNum)) continue;
    const instances = rawInstances
      .map((item, idx) => ({
        key: `${verseNum}:${idx}`,
        text: String(item?.text || "").trim(),
        replacement: String(item?.replacement || "").trim(),
      }))
      .filter(item => item.text && item.replacement);
    if (instances.length) byVerse.set(verseNum, instances);
  }
  return byVerse;
}

function findNextEntityMatch(text, matcher, cursor) {
  if (!matcher) return null;
  matcher.regex.lastIndex = cursor;
  const match = matcher.regex.exec(text);
  if (!match) return null;
  const entity = matcher.entityByTerm.get(match[0].toLocaleLowerCase());
  return {
    index: match.index,
    length: match[0].length,
    content: match[0],
    entityName: entity?.name || match[0],
    entityType: entity?.entityType || null,
  };
}

function findNextPronounMatch(text, pronounInstances, pronounIndex, cursor) {
  const instance = pronounInstances[pronounIndex];
  if (!instance) return null;
  const regex = new RegExp(`(?<!${ENTITY_TEXT_BOUNDARY})(${escapeRegExp(instance.text)})(?!${ENTITY_TEXT_BOUNDARY})`, "iu");
  const remainder = text.slice(cursor);
  const match = regex.exec(remainder);
  if (!match) return null;
  return {
    index: cursor + match.index,
    length: match[0].length,
    content: match[0],
    pronounKey: instance.key,
    replacement: instance.replacement,
  };
}

// Split verse HTML into alternating {type:'html'|'entity'|'pronoun'} segments
function parseVerseHtml(html, allEntities, pronounInstances = []) {
  const matcher = buildEntityMatcher(allEntities);
  const segments = [];
  let htmlAccum = "";
  let pronounIndex = 0;
  for (const part of html.split(/(<[^>]+>)/)) {
    if (part.startsWith("<")) {
      htmlAccum += part;
    } else {
      let cursor = 0;
      while (cursor < part.length) {
        const nextEntity = findNextEntityMatch(part, matcher, cursor);
        const nextPronoun = findNextPronounMatch(part, pronounInstances, pronounIndex, cursor);
        const nextMatch = !nextPronoun
          ? nextEntity
          : !nextEntity
            ? nextPronoun
            : nextPronoun.index <= nextEntity.index
              ? nextPronoun
              : nextEntity;

        if (!nextMatch) {
          htmlAccum += part.slice(cursor);
          break;
        }

        htmlAccum += part.slice(cursor, nextMatch.index);
        if (htmlAccum) {
          segments.push({ type: "html", content: htmlAccum });
          htmlAccum = "";
        }

        if (nextMatch.pronounKey) {
          segments.push({ type: "pronoun", ...nextMatch });
          pronounIndex += 1;
        } else {
          segments.push({ type: "entity", ...nextMatch });
        }
        cursor = nextMatch.index + nextMatch.length;
      }
    }
  }
  if (htmlAccum) segments.push({ type: "html", content: htmlAccum });
  return segments;
}

// Split non-verse HTML into alternating {type:'html'|'entity'} segments
function parseHtmlWithEntities(html, allEntities) {
  return parseVerseHtml(html, allEntities, []).filter(seg => seg.type !== "pronoun");
}

// Renders verse HTML with entity and pronoun interactions.
function VerseText({ html, allEntities, pronounInstances, revealedPronouns, onPronounReveal, onEntityClick, className }) {
  const segments = useMemo(
    () => (allEntities.length || pronounInstances.length) ? parseVerseHtml(html, allEntities, pronounInstances) : null,
    [html, allEntities, pronounInstances]
  );
  if (!segments) {
    return <span className={className} dangerouslySetInnerHTML={{ __html: html }} />;
  }
  return (
    <span className={className}>
      {segments.map((seg, i) => {
        if (seg.type === "entity") {
          return (
            <span
              key={i}
              onClick={() => onEntityClick(seg.entityName)}
              style={getEntityLinkStyle(seg.entityType)}
            >
              {seg.content}
            </span>
          );
        }
        if (seg.type === "pronoun") {
          const isRevealed = !!revealedPronouns?.[seg.pronounKey];
          return (
            <span
              key={i}
              onClick={isRevealed ? undefined : () => onPronounReveal(seg.pronounKey)}
              style={isRevealed ? getPronounReplacementStyle() : getEntityLinkStyle("pronoun")}
            >
              {isRevealed ? seg.replacement : seg.content}
            </span>
          );
        }
        return <span key={i} dangerouslySetInnerHTML={{ __html: seg.content }} />;
      })}
    </span>
  );
}

function parseEntities(text, entityType = null) {
  if (!text) return [];
  const lines = text.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  const sections = [];
  for (const line of lines) {
    const m = line.match(ENTITY_HEADER_RE);
    if (m) {
      const trailing = m[2].replace(/^[\s:—–-]+/, "").trim();
      const name = normalizeEntityName(m[1]);
      sections.push({ name, entityType, aliases: getEntityAliases(name), body: trailing ? [trailing] : [] });
    } else if (sections.length > 0) {
      sections[sections.length - 1].body.push(line);
    }
  }
  return sections.filter(s => s.name);
}

function injectEntityLinks(html, entities) {
  const matcher = buildEntityMatcher(entities);
  if (!matcher) return html;
  const { regex, entityByTerm } = matcher;
  // Only replace inside text nodes (not inside HTML tag attribute strings)
  const parts = html.split(/(<[^>]+>)/);
  return parts
    .map(part => {
      if (part.startsWith("<")) return part;
      return part.replace(regex, (match) => {
        const entity = entityByTerm.get(match.toLocaleLowerCase());
        const entityName = (entity?.name || match).replace(/"/g, "&quot;");
        const style = Object.entries(getEntityLinkStyle(entity?.entityType))
          .map(([key, value]) => `${key}:${value}`)
          .join(";");
        return `<span data-entity="${entityName}" onclick="window.__eClick&&window.__eClick(this.dataset.entity)" style="${style}">${match}</span>`;
      });
    })
    .join("");
}

// ═════════════════════════════════════════════════════════════════════════════
//  LLM Content (shared renderer for Summary / People / Places)
// ═════════════════════════════════════════════════════════════════════════════

function LlmContent({ content, isLoading, loadingLabel, emptyLabel, fs, collapsible, allEntities, onEntityClick }) {
  const [openIdx, setOpenIdx] = useState(null);

  // Reset open section when content changes
  useEffect(() => { setOpenIdx(null); }, [content]);

  if (isLoading) {
    return (
      <div className="flex items-center gap-3 py-12 justify-center">
        <Loader2 className="animate-spin text-teal-400" size={28} />
        <span className={`${fs.summary} text-gray-400`}>{loadingLabel}</span>
      </div>
    );
  }
  if (!content) {
    return <p className="text-gray-500 text-lg">{emptyLabel}</p>;
  }

  // Plain paragraph rendering (summary)
  if (!collapsible) {
    const entities = allEntities || [];
    return (
      <div className={`${fs.summary} text-gray-200 leading-normal`}>
        {content.split(/\n+/).filter(p => p.trim()).map((para, i) => {
          const html = para.replace(/\*\*(.+?)\*\*/g, '<strong class="text-teal-300">$1</strong>');
          if (!entities.length || !onEntityClick) {
            return <div key={i} className="mb-6" dangerouslySetInnerHTML={{ __html: html }} />;
          }
          const segments = parseHtmlWithEntities(html, entities);
          return (
            <div key={i} className="mb-6">
              {segments.map((seg, j) =>
                seg.type === 'entity' ? (
                  <span
                    key={j}
                    onClick={() => onEntityClick(seg.entityName)}
                    style={getEntityLinkStyle(seg.entityType)}
                  >
                    {seg.content}
                  </span>
                ) : (
                  <span key={j} dangerouslySetInnerHTML={{ __html: seg.content }} />
                )
              )}
            </div>
          );
        })}
      </div>
    );
  }

  // Collapsible accordion: split content into sections by **Name** headers
  const sections = [];
  const lines = content.split(/\r?\n/).map(l => l.trim()).filter(Boolean);
  for (const line of lines) {
    const nameMatch = line.match(/^\*\*(.+?)\*\*(.*)$/);
    if (nameMatch) {
      const trailing = nameMatch[2].replace(/^[\s:—–-]+/, "").trim();
      sections.push({ name: nameMatch[1], body: trailing ? [trailing] : [] });
    } else if (sections.length > 0) {
      sections[sections.length - 1].body.push(line);
    } else {
      // Text before any **Name** header — treat as a standalone section
      sections.push({ name: null, body: [line] });
    }
  }

  // Sort named sections alphabetically, skipping leading articles
  const SKIP_WORDS = /^(the|a|an)\s+/i;
  const sortKey = (name) => (name || "").replace(SKIP_WORDS, "").toLowerCase();
  sections.sort((a, b) => {
    if (!a.name) return -1;
    if (!b.name) return -1;
    return sortKey(a.name).localeCompare(sortKey(b.name));
  });

  return (
    <div className="space-y-1">
      {sections.map((sec, i) => {
        const isOpen = openIdx === i;
        // Sections without a name header render as plain paragraphs
        if (!sec.name) {
          return (
            <div key={i} className={`${fs.summary} text-gray-200 leading-normal mb-4`}>
              {sec.body.map((p, j) => <div key={j} className="mb-2">{p}</div>)}
            </div>
          );
        }
        return (
          <div key={i} className="border border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setOpenIdx(isOpen ? null : i)}
              className="w-full flex items-center gap-2 px-4 py-3 text-left bg-gray-800 hover:bg-gray-750 transition-colors"
            >
              <ChevronDown
                size={18}
                className={`text-gray-400 shrink-0 transition-transform duration-200 ${
                  isOpen ? "rotate-0" : "-rotate-90"
                }`}
              />
              <span className={`${fs.summary} font-semibold text-teal-300 leading-snug`}>
                {sec.name}
              </span>
            </button>
            {isOpen && (
              <div className={`${fs.summary} text-gray-200 leading-normal px-4 py-3 border-t border-gray-700 bg-gray-800/50`}>
                {sec.body.map((p, j) => (
                  <div key={j} className="mb-3" dangerouslySetInnerHTML={{
                    __html: p.replace(/\*\*(.+?)\*\*/g, '<strong class="text-teal-300">$1</strong>')
                  }} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}


// ═════════════════════════════════════════════════════════════════════════════
//  Entity Detail Modal
// ═════════════════════════════════════════════════════════════════════════════

function EntityModal({ entityName, allEntities, onClose, fs }) {
  const info = allEntities.find(
    e => e.name.toLowerCase() === entityName.toLowerCase()
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
      onClick={onClose}
    >
      <div
        className="bg-gray-800 border border-gray-600 rounded-xl shadow-2xl w-[90vw] max-w-2xl max-h-[70vh] flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-700 shrink-0">
          <h3 className={`${fs.summary} font-bold text-teal-300 leading-snug`}>{entityName}</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white ml-4 shrink-0">
            <X size={22} />
          </button>
        </div>
        {/* Body */}
        <div className={`${fs.summary} text-gray-200 leading-relaxed px-5 py-4 overflow-y-auto`}>
          {info && info.body.length > 0 ? (
            info.body.map((para, i) => (
              <p key={i} className="mb-3" dangerouslySetInnerHTML={{
                __html: para.replace(/\*\*(.+?)\*\*/g, '<strong class="text-teal-300">$1</strong>')
              }} />
            ))
          ) : (
            <p className="text-gray-500">No additional information available.</p>
          )}
        </div>
      </div>
    </div>
  );
}


// ═════════════════════════════════════════════════════════════════════════════
//  Book Picker
// ═════════════════════════════════════════════════════════════════════════════

function BookPicker({ books, currentBook, onSelect, onClose }) {
  const otBooks = books.filter(b => b.testament === "OT");
  const ntBooks = books.filter(b => b.testament === "NT");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 w-[90vw] max-w-2xl max-h-[80vh] overflow-y-auto"
        onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold text-white">Select Book</h3>
          <button onClick={onClose} className="text-gray-400 hover:text-white"><X size={20} /></button>
        </div>

        <h4 className="text-sm font-semibold text-gray-400 mb-2">Old Testament</h4>
        <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5 mb-4">
          {otBooks.map(b => (
            <button key={b.book_number} onClick={() => onSelect(b.book_number)}
              className={`px-2 py-2 text-xs rounded text-center truncate ${
                b.book_number === currentBook
                  ? "bg-teal-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
              title={`${b.name} (${b.name_english})`}>
              {b.abbreviation}
            </button>
          ))}
        </div>

        <h4 className="text-sm font-semibold text-gray-400 mb-2">New Testament</h4>
        <div className="grid grid-cols-4 sm:grid-cols-6 gap-1.5">
          {ntBooks.map(b => (
            <button key={b.book_number} onClick={() => onSelect(b.book_number)}
              className={`px-2 py-2 text-xs rounded text-center truncate ${
                b.book_number === currentBook
                  ? "bg-teal-600 text-white"
                  : "bg-gray-700 text-gray-300 hover:bg-gray-600"
              }`}
              title={`${b.name} (${b.name_english})`}>
              {b.abbreviation}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}


// ═════════════════════════════════════════════════════════════════════════════
//  Search Tab
// ═════════════════════════════════════════════════════════════════════════════

function SearchTab({ versionId, goToVerse, fs }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [searching, setSearching] = useState(false);
  const timerRef = useRef(null);

  const doSearch = useCallback(async (q) => {
    if (!q || q.length < 3 || !versionId) return;
    setSearching(true);
    try {
      const res = await fetch(`${API}/search?version_id=${versionId}&q=${encodeURIComponent(q)}&limit=50`);
      const data = await res.json();
      setResults(data.results || []);
      setTotal(data.total || 0);
    } catch (e) { console.error("Search failed", e); }
    setSearching(false);
  }, [versionId]);

  const handleInput = (val) => {
    setQuery(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(val), 400);
  };

  return (
    <div className="p-4 space-y-4">
      <div className="relative">
        <Search size={18} className="absolute left-3 top-2.5 text-gray-500" />
        <input type="text" value={query} onChange={e => handleInput(e.target.value)}
          placeholder="Search the scriptures (min 3 characters)…"
          className="w-full text-lg bg-gray-800 border border-gray-600 rounded-lg pl-10 pr-4 py-2.5 text-gray-200 focus:outline-none focus:border-teal-500" />
      </div>

      {searching && (
        <div className="flex items-center gap-2 text-gray-400">
          <Loader2 className="animate-spin" size={18} /> Searching…
        </div>
      )}

      {!searching && results.length > 0 && (
        <p className="text-sm text-gray-500">{total} result{total !== 1 ? "s" : ""}</p>
      )}

      <div className="space-y-3">
        {results.map((r, i) => {
          const ref = `${r.book_name || r.book_name_english} ${r.chapter}:${r.verse}`;
          // Highlight search term in text
          const highlighted = query
            ? r.text.replace(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"), "<mark class='bg-teal-700 text-white rounded px-0.5'>$1</mark>")
            : r.text;
          return (
            <button key={i} onClick={() => goToVerse(r.book, r.chapter)}
              className="w-full text-left p-3 rounded-lg bg-gray-800 hover:bg-gray-750 border border-gray-700 hover:border-gray-600 transition-colors">
              <div className="text-sm font-semibold text-teal-400 mb-1">{ref}</div>
              <div className={`${fs.verse === "text-4xl" ? "text-lg" : "text-base"} text-gray-300 leading-relaxed`}
                dangerouslySetInnerHTML={{ __html: highlighted }} />
            </button>
          );
        })}
      </div>

      {!searching && query.length >= 3 && results.length === 0 && (
        <p className="text-gray-500 text-center py-8">No results found for "{query}"</p>
      )}
    </div>
  );
}


// ═════════════════════════════════════════════════════════════════════════════
//  Bookmarks Tab
// ═════════════════════════════════════════════════════════════════════════════

function BookmarksTab({ versionId, userId, goToBookmark }) {
  const [bookmarks, setBookmarks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newColor, setNewColor] = useState("blue");
  const [deleting, setDeleting] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/bookmarks`);
      const data = await res.json();
      setBookmarks(data.bookmarks || []);
    } catch (e) { console.error("Failed to load bookmarks", e); }
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleCreate = async () => {
    if (!newName.trim()) return;
    try {
      await fetch(`${API}/bookmarks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          version_id: versionId,
          book: 1,
          chapter: 1,
          color: newColor,
          user_id: userId || "",
        }),
      });
      setNewName("");
      setShowCreate(false);
      load();
    } catch (e) { console.error("Failed to create bookmark", e); }
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`${API}/bookmarks/${id}`, { method: "DELETE" });
      setDeleting(null);
      load();
    } catch (e) { console.error("Failed to delete bookmark", e); }
  };

  if (loading) {
    return <div className="flex items-center justify-center py-16"><Loader2 className="animate-spin text-gray-500" size={32} /></div>;
  }

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-bold text-white">Reading Positions</h3>
        <button onClick={() => setShowCreate(s => !s)} className={btnPrimary}>
          <Plus size={16} /> New Bookmark
        </button>
      </div>

      {/* Create form */}
      {showCreate && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 space-y-3">
          <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
            placeholder={'e.g. "Family Reading" or "Morning Reading"'}
            className={inp} autoFocus
            onKeyDown={e => e.key === "Enter" && handleCreate()} />
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Color:</span>
            {BOOKMARK_COLORS.map(c => (
              <button key={c} onClick={() => setNewColor(c)}
                className={`w-6 h-6 rounded-full ${COLOR_MAP[c]} ${
                  newColor === c ? "ring-2 ring-white ring-offset-2 ring-offset-gray-800" : ""
                }`} />
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={handleCreate} disabled={!newName.trim()} className={btnPrimary}>Create</button>
            <button onClick={() => setShowCreate(false)} className={btnSecondary}>Cancel</button>
          </div>
        </div>
      )}

      {/* Bookmark list */}
      {bookmarks.length === 0 && !showCreate && (
        <p className="text-gray-500 text-center py-8">No bookmarks yet. Create one to track your reading position.</p>
      )}

      <div className="space-y-2">
        {bookmarks.map(bm => (
          <div key={bm.id} className="flex items-center gap-3 p-3 bg-gray-800 border border-gray-700 rounded-lg hover:border-gray-600">
            <div className={`w-3 h-3 rounded-full shrink-0 ${COLOR_MAP[bm.color] || COLOR_MAP.blue}`} />

            <div className="flex-1 min-w-0">
              <div className="font-semibold text-white text-base">{bm.name}</div>
              <div className="text-sm text-gray-400">
                {bm.book_name ? `${bm.book_name} (${bm.book_name_english})` : `Book ${bm.book}`} {bm.chapter}
                {bm.updated_by && <span className="ml-2 text-gray-600">· moved by {bm.updated_by}</span>}
              </div>
            </div>

            <button onClick={() => goToBookmark(bm)}
              className="px-3 py-1.5 text-sm rounded bg-teal-700 hover:bg-teal-600 text-white shrink-0">
              Go to
            </button>

            {deleting === bm.id ? (
              <div className="flex items-center gap-1">
                <button onClick={() => handleDelete(bm.id)} className="px-2 py-1 text-xs rounded bg-red-600 text-white">Yes</button>
                <button onClick={() => setDeleting(null)} className="px-2 py-1 text-xs rounded bg-gray-600 text-gray-300">No</button>
              </div>
            ) : (
              <button onClick={() => setDeleting(bm.id)} className="text-gray-600 hover:text-red-400">
                <Trash2 size={16} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
