import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router';
import '@fontsource-variable/fraunces/full.css';
import '@fontsource-variable/fraunces/full-italic.css';
import '@fontsource-variable/dm-sans';
import './styles/base.css';
import './styles/tv.css';
import './styles/phone.css';
import './styles/dev.css';
import { router } from './router';
import { RoomProvider } from './room/RoomProvider';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RoomProvider>
      <RouterProvider router={router} />
    </RoomProvider>
  </StrictMode>,
);
