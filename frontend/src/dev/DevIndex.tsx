// Dev-only index of every screen, so anyone can jump straight to one.

import { Link } from 'react-router';
import { Smartphone, Tv } from 'lucide-react';
import { QR, Wordmark } from '../components/ui';

const TV_SCREENS = [
  ['/tv/lobby', 'Lobby with QR code'],
  ['/tv/trailer/1', 'Trailer'],
  ['/tv/vote/1', 'Vote on your phone'],
  ['/tv/reveal/1', 'The verdict'],
  ['/tv/miss/1', 'Not this one'],
  ['/tv/buzzer/2', 'Golden buzzer'],
  ['/tv/checkpoint/5', 'Checkpoint after 5 trailers'],
  ['/tv/picks', 'Top 3 + 5 more'],
  ['/tv/showing/195159', 'Now showing'],
];

const PHONE_SCREENS = [
  ['/phone/join?room=K7Q2', 'Join (scanned QR)'],
  ['/phone/join', 'Join (type a code)'],
  ['/phone/sign-in', 'Sign in with Google'],
  ['/phone/feeling', "Tonight’s feeling"],
  ['/phone/screenshots', 'Explore screenshots'],
  ['/phone/reading', 'Reading your feed'],
  ['/phone/lobby', 'Waiting room'],
  ['/phone/react/1', 'React during a trailer'],
  ['/phone/vote/1', 'Vote'],
  ['/phone/voted/1?vote=yes', 'Voted, waiting'],
  ['/phone/miss/1', 'Not this one'],
  ['/phone/buzzer/2', 'Golden buzzer'],
  ['/phone/checkpoint/5', 'Checkpoint'],
  ['/phone/picks', 'Top 3 + 5 more'],
  ['/phone/showing/195159', 'Now showing'],
];

export function DevIndex() {
  const phoneUrl = `${__LAN_ORIGIN__ || location.origin}/phone/join?room=K7Q2`;
  return (
    <main className="dev-index">
      <header>
        <Wordmark className="dev-wordmark" />
        <p>
          Every screen, with mock data. Arrows on the right edge of any screen step through the night. Nothing talks to the
          backend yet.
        </p>
      </header>
      <div className="dev-cols">
        <section>
          <h2>
            <Tv aria-hidden="true" /> Big screen
          </h2>
          <ul>
            {TV_SCREENS.map(([to, label]) => (
              <li key={to}>
                <Link to={to}>{label}</Link>
                <code>{to}</code>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <h2>
            <Smartphone aria-hidden="true" /> Phone
          </h2>
          <ul>
            {PHONE_SCREENS.map(([to, label]) => (
              <li key={to}>
                <Link to={to}>{label}</Link>
                <code>{to}</code>
              </li>
            ))}
          </ul>
        </section>
        <aside className="dev-qr">
          <QR text={phoneUrl} />
          <p>Scan with a phone on the same Wi-Fi to open the phone flow.</p>
          <code>{phoneUrl}</code>
        </aside>
      </div>
    </main>
  );
}
