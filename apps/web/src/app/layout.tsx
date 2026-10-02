import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import './globals.css';

export const metadata: Metadata = {
  title: 'RAG Chatbot',
  description: 'Ask questions about the indexed document corpus.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main className="page">{children}</main>
      </body>
    </html>
  );
}