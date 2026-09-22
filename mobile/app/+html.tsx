import { ScrollViewStyleReset } from 'expo-router/html';
import type { ReactNode } from 'react';

import { darkColors, lightColors } from '@/theme/tokens';

export default function Root({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <head>
        <meta charSet="utf-8" />
        <meta httpEquiv="X-UA-Compatible" content="IE=edge" />
        <meta
          name="viewport"
          content="width=device-width, initial-scale=1, shrink-to-fit=no"
        />
        <ScrollViewStyleReset />
        <style
          dangerouslySetInnerHTML={{
            __html: `body { background-color: ${darkColors.background}; } @media (prefers-color-scheme: light) { body { background-color: ${lightColors.background}; } }`,
          }}
        />
      </head>
      <body>{children}</body>
    </html>
  );
}
