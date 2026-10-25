// The demo stage: big screen and phone side by side, plus a look switcher.

const THEMES = [
  { id: 'velvet', label: 'Velvet', swatch: ['#140b0e', '#d12f45', '#f4c55a'] },
  { id: 'neon', label: 'Neon', swatch: ['#080716', '#ff3ea5', '#2ee6e6'] },
  { id: 'matinee', label: 'Matinee', swatch: ['#f6efe2', '#e1452c', '#211b14'] },
];

function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      return localStorage.getItem('tandem-theme') || 'velvet';
    } catch (e) {
      return 'velvet';
    }
  });
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem('tandem-theme', theme);
    } catch (e) {}
  }, [theme]);
  return [theme, setTheme];
}

function stageHint({ s, unanimous }) {
  if (s.phase === 'lobby') {
    if (s.phoneStep === 'scan') return 'Click the QR code on the big screen (or "Scan" on the phone) to join.';
    if (s.phoneStep !== 'seated') return 'Finish joining on the phone. Your friends are scanning in on their own.';
    return 'Start the show from the phone or the big screen.';
  }
  if (s.phase === 'trailer') return 'Tap emotes on the phone and watch them float up on the big screen.';
  if (s.phase === 'voting') return 'Vote on the phone. It only counts if everyone says yes.';
  if (s.phase === 'reveal') return 'Revealing the votes…';
  if (s.phase === 'result') {
    return unanimous ? 'Golden buzzer. Start the movie, or keep browsing.' : 'Someone passed, so the next trailer loads on its own.';
  }
  return 'Restart to run the demo again.';
}

function App() {
  const night = useMovieNight();
  const [theme, setTheme] = useTheme();
  return (
    <div className="stage">
      <header className="toolbar">
        <div className="toolbar-brand">
          <Wordmark />
          <span className="pill">Demo UI</span>
        </div>
        <div className="toolbar-controls">
          <div className="segmented" role="radiogroup" aria-label="Look">
            {THEMES.map((t) => (
              <button key={t.id} role="radio" aria-checked={theme === t.id} onClick={() => setTheme(t.id)}>
                <span className="swatch" aria-hidden="true">
                  {t.swatch.map((c) => (
                    <i key={c} style={{ background: c }} />
                  ))}
                </span>
                {t.label}
              </button>
            ))}
          </div>
          <button
            className="tool-btn"
            disabled={night.s.phase !== 'trailer'}
            onClick={() => night.dispatch({ type: 'endTrailer' })}
          >
            <Icon name="skip" /> Skip trailer
          </button>
          <button className="tool-btn" onClick={() => night.dispatch({ type: 'restart' })}>
            <Icon name="restart" /> Restart
          </button>
        </div>
      </header>

      <main className="room">
        <figure className="device device--tv">
          <figcaption>
            Big screen <span>TV, laptop or projector</span>
          </figcaption>
          <TV night={night} />
        </figure>
        <figure className="device device--phone">
          <figcaption>
            Phone <span>one per friend</span>
          </figcaption>
          <Phone night={night} />
        </figure>
      </main>

      <p className="stage-hint">{stageHint(night)}</p>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
