// Dev-only home: open the big screen, get phones in, and jump the room
// straight to any screen for review.

import { useNavigate } from 'react-router';
import { Smartphone, Tv, Users } from 'lucide-react';
import { act } from '../api';
import { QR, Wordmark } from '../components/ui';
import { useRoom } from '../room/useRoom';

const JUMPS = [
  ['lobby', 'Lobby with QR code'],
  ['trailer', 'Trailer'],
  ['vote', 'Vote on your phone'],
  ['reveal', 'The verdict'],
  ['miss', 'Not this one'],
  ['buzzer', 'Golden buzzer'],
  ['checkpoint', 'Checkpoint after 5 trailers'],
  ['picks', 'Top 3 + 5 more'],
  ['showing', 'Now showing'],
];

export function DevIndex() {
  const { s } = useRoom();
  const navigate = useNavigate();
  const phoneUrl = `${__LAN_ORIGIN__ || location.origin}/phone/join?room=${s.code}`;
  const jump = async (screen: string) => {
    await act('devGoto', { screen });
    navigate('/tv');
  };
  return (
    <main className="dev-index">
      <header>
        <Wordmark className="dev-wordmark" />
        <p>
          A fake backend runs inside this dev server, so the big screen and every phone share one live room. Open the big
          screen on the laptop, then have everyone scan the QR code.
        </p>
      </header>
      <div className="dev-cols">
        <section>
          <h2>
            <Tv aria-hidden="true" /> Big screen
          </h2>
          <p className="dev-note">
            <a href="/tv">Open the big screen</a>. Or jump the room to a screen (empty seats get test friends):
          </p>
          <ul>
            {JUMPS.map(([screen, label]) => (
              <li key={screen}>
                <button className="dev-link" onClick={() => jump(screen)}>
                  {label}
                </button>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>
            <Users aria-hidden="true" /> Room {s.code}
          </h2>
          <p className="dev-note">
            {s.people.length
              ? `${s.people.length} in the room: ${s.people.map((p) => p.name + (p.seated ? '' : ' (joining)')).join(', ')}.`
              : 'Nobody here yet.'}{' '}
            Now: {s.phase}
            {s.round ? `, trailer ${s.round}` : ''}.
          </p>
          <div className="dev-actions">
            <button className="dev-link" onClick={() => act('devFill')}>
              Fill seats with test friends
            </button>
            <button className="dev-link" onClick={() => act('newNight')}>
              New night, same people
            </button>
            <button className="dev-link" onClick={() => act('reset')}>
              Reset the room
            </button>
          </div>
          <h2 className="dev-h2-gap">
            <Smartphone aria-hidden="true" /> Phone
          </h2>
          <p className="dev-note">
            <a href="/phone/join?room=K7Q2">Open the phone flow here</a>. Each browser tab is its own person, so you can
            test with a few tabs.
          </p>
        </section>
        <aside className="dev-qr">
          <QR text={phoneUrl} />
          <p>Scan with a phone on the same Wi-Fi to join.</p>
          <code>{phoneUrl}</code>
        </aside>
      </div>
    </main>
  );
}
