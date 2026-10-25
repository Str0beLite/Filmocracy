// Dev-only home: how to run a night against the local backend.

import { Smartphone, Tv } from 'lucide-react';
import { Wordmark } from '../components/ui';

export function DevIndex() {
  return (
    <main className="dev-index">
      <header>
        <Wordmark className="dev-wordmark" />
        <p>
          The app talks to the real backend (start it on port 8000; this dev server forwards /api to it). Open the big
          screen on the laptop, then have everyone scan its QR code.
        </p>
      </header>
      <div className="dev-cols">
        <section>
          <h2>Train Your Taste</h2>
          <p className="dev-note"><a href="/training">Open training</a>. Upload 3 Explore screenshots, watch trailers, and vote without joining a room.</p>
        </section>
        <section>
          <h2>
            <Tv aria-hidden="true" /> Big screen
          </h2>
          <p className="dev-note">
            <a href="/tv">Open the big screen</a>. It creates a session and shows the QR code to join it. The fast-forward
            button on its right edge moves the night along.
          </p>
        </section>
        <section>
          <h2>
            <Smartphone aria-hidden="true" /> Phone
          </h2>
          <p className="dev-note">
            Scan the QR code, or open its link in another browser tab. Each tab is its own person, so you can test a whole
            group on one laptop.
          </p>
        </section>
      </div>
    </main>
  );
}
