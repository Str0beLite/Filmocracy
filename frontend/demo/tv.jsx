// The big screen: lobby with QR, trailer, verdict, golden buzzer.

function TV({ night }) {
  const { s, unanimous } = night;
  const view =
    s.phase === 'lobby'
      ? 'lobby'
      : s.phase === 'showing'
        ? 'showing'
        : s.phase === 'result' && unanimous
          ? 'buzzer'
          : 'trailer';
  return (
    <div className={`tv is-${view}`}>
      <div className="tv-bezel">
        <div className="tv-screen">
          {view === 'lobby' && <TVLobby night={night} />}
          {view === 'trailer' && <TVTrailer key={s.movieIdx} night={night} />}
          {view === 'buzzer' && <TVBuzzer night={night} />}
          {view === 'showing' && <TVShowing night={night} />}
          <Curtains open={view === 'trailer' || view === 'showing'} />
        </div>
      </div>
      <div className="tv-stand" />
    </div>
  );
}

function Curtains({ open }) {
  return (
    <div className={`curtains ${open ? 'is-open' : ''}`} aria-hidden="true">
      <div className="curtain curtain--left" />
      <div className="curtain curtain--right" />
      <div className="valance" />
    </div>
  );
}

function TVLobby({ night }) {
  const { s, dispatch, everyoneSeated, start } = night;
  const missing = D.people.filter((p) => !s.seated.includes(p.id)).length;
  return (
    <div className="lobby">
      <div className="lobby-top">
        <Wordmark />
        <span className="room-pill">
          <span className="live-dot" />
          {D.room.name}
        </span>
      </div>

      <div className="lobby-main">
        <div>
          <p className="eyebrow">Room {D.room.code}</p>
          <h1 className="lobby-title">Grab a seat.</h1>
          <p className="lobby-sub">
            Scan the code with your phone. Tandem reads the room's taste and plays trailers you might all say yes to.
          </p>
          <ol className="lobby-steps">
            <li><b>1</b>Scan</li>
            <li><b>2</b>Connect Instagram</li>
            <li><b>3</b>Vote on trailers</li>
          </ol>
        </div>
        <button className="qr-card" onClick={() => dispatch({ type: 'scan' })} title="Demo: click to scan with the phone">
          <QR text={`https://tandem.example/j/${D.room.code}`} />
          <span className="qr-label">Scan to join</span>
        </button>
      </div>

      <div className="lobby-foot">
        <div className="seat-row">
          {D.people.map((p) => (
            <Seat key={p.id} person={p} s={s} status={seatStatus(p, s)} showVibe />
          ))}
        </div>
        <button className="tv-btn tv-btn--primary" disabled={!everyoneSeated} onClick={start}>
          {everyoneSeated ? (
            <>
              Start the show <Icon name="arrow" />
            </>
          ) : (
            `Waiting for ${missing} more`
          )}
        </button>
      </div>
    </div>
  );
}

function TVTrailer({ night }) {
  const { s, movie } = night;
  const now = useNow(s.phase === 'trailer');
  const p = trailerProgress(s, now);
  const shot = Math.min(2, Math.floor(p * 3));
  const verdict = s.phase !== 'trailer';
  const names = D.people.map((person) => displayName(person, s));
  const [c1, c2, c3] = movie.palette;
  const byId = Object.fromEntries(D.people.map((person) => [person.id, person]));

  return (
    <div className={`trailer ${verdict ? 'is-verdict' : ''}`} style={{ '--c1': c1, '--c2': c2, '--c3': c3 }}>
      <div className={`scene ${verdict ? 'is-paused' : ''}`}>
        {['a', 'b', 'c'].map((k, i) => (
          <div key={k} className={`shot shot--${k} ${shot === i ? 'is-on' : ''}`} />
        ))}
        <div className="vignette" />
        <div className="grain" />
        <p className={`scene-caption ${p < 0.22 ? 'is-on' : ''}`}>
          Picked for {names.slice(0, -1).join(', ')} & {names[names.length - 1]}
        </p>
        <div className={`title-card ${p > 0.45 && p < 0.8 ? 'is-on' : ''}`}>
          <h3>{movie.title}</h3>
          <span>{movie.year}</span>
        </div>
      </div>
      <div className="letterbox letterbox--top" />
      <div className="letterbox letterbox--bottom" />

      <div className="trailer-top">
        <span className="chip">
          <Icon name="play" /> Trailer {s.movieIdx + 1} · <b>{movie.match}% group match</b>
        </span>
        <Wordmark />
      </div>

      <div className="trailer-info">
        <h2 className="trailer-title">{movie.title}</h2>
        <p className="trailer-meta">
          {movie.year} · {movie.runtime} · {movie.genres.join(', ')}
        </p>
        <div className="why">
          <span className="why-label">Why it's here</span>
          {movie.why.map((w) => (
            <span className="chip" key={w.who}>
              <Avatar person={byId[w.who]} s={s} />
              {displayName(byId[w.who], s)} {w.text}
            </span>
          ))}
        </div>
        <div className="progress">
          <div className="progress-track">
            <i style={{ width: `${p * 100}%` }} />
          </div>
          <span>
            {fmtTime(p * TRAILER_MS)} / {fmtTime(TRAILER_MS)}
          </span>
        </div>
      </div>

      <div className="trailer-seats">
        {D.people.map((person) => (
          <Seat key={person.id} person={person} s={s} size="sm">
            {s.reactions
              .filter((r) => r.who === person.id)
              .map((r) => (
                <span key={r.id} className="reaction" style={{ '--dx': r.dx }}>
                  {r.emoji}
                </span>
              ))}
          </Seat>
        ))}
      </div>

      {verdict && <TVVerdict night={night} />}
    </div>
  );
}

function TVVerdict({ night }) {
  const { s, movie, voteCount, yesCount, revealOrder } = night;
  const total = D.people.length;
  const stage = s.phase === 'result' ? 'miss' : s.phase;
  const copy = {
    voting: { eyebrow: "Trailer's over", title: 'Vote on your phone', sub: `${voteCount} of ${total} locked in` },
    reveal: { eyebrow: movie.title, title: 'The verdict…', sub: 'Everyone has to say yes' },
    miss: { eyebrow: 'No golden buzzer this time', title: `So close. ${yesCount} of ${total}.`, sub: 'Next trailer coming up' },
  }[stage];

  return (
    <div className={`verdict verdict--${stage}`}>
      <p className="eyebrow">{copy.eyebrow}</p>
      <h2 className="verdict-title">{copy.title}</h2>
      <div className="seat-row">
        {D.people.map((p) => {
          const shown = stage !== 'voting' && revealOrder.indexOf(p.id) < s.revealed;
          const badge = shown ? s.votes[p.id] : s.votes[p.id] ? 'locked' : 'thinking';
          return <Seat key={p.id} person={p} s={s} badge={badge} />;
        })}
      </div>
      <p className="verdict-sub">{copy.sub}</p>
      {stage === 'miss' && <div className="countdown" style={{ animationDuration: `${MISS_PAUSE_MS}ms` }} />}
    </div>
  );
}

function TVBuzzer({ night }) {
  const { s, movie, dispatch, nextTrailer } = night;
  return (
    <div className="buzzer">
      <div className="buzzer-rays" />
      <Confetti count={90} />
      <div className="buzzer-head">
        <p className="eyebrow">
          {D.people.length} of {D.people.length} said yes
        </p>
        <h1 className="buzzer-title gold-text">Golden Buzzer</h1>
      </div>
      <div className="buzzer-body">
        <Poster movie={movie} />
        <div className="buzzer-pick">
          <p className="eyebrow">Tonight's movie</p>
          <h2>{movie.title}</h2>
          <p className="buzzer-meta">
            {movie.year} · {movie.runtime} · {movie.genres.join(', ')}
          </p>
          <p className="buzzer-logline">{movie.logline}</p>
          <div className="buzzer-crew">
            {D.people.map((p) => (
              <span className="buzzer-crew-member" key={p.id}>
                <Avatar person={p} s={s} />
                <Icon name="check" />
              </span>
            ))}
          </div>
          <div className="buzzer-actions">
            <button className="tv-btn tv-btn--gold" onClick={() => dispatch({ type: 'showMovie' })}>
              <Icon name="play" /> Start the movie
            </button>
            <button className="tv-btn tv-btn--ghost" onClick={nextTrailer}>
              Keep browsing
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function TVShowing({ night }) {
  return (
    <div className="showing">
      <p className="eyebrow">Now showing</p>
      <h2>{night.movie.title}</h2>
      <p className="showing-sub">Lights down. Phones away.</p>
    </div>
  );
}
