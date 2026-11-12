import type { Metadata } from 'next';
import { Sidebar } from '@/components/layout/Sidebar';
import './globals.css';

export const metadata: Metadata = {
  title: 'RAG Intelligence — Enterprise Platform',
  description: 'Evidence-grounded multi-modal enterprise AI research platform',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="bg-[#F7F9FC] text-[#172B4D] min-h-screen">
        <div className="flex">
          <Sidebar />
          <main className="flex-1 ml-64 p-8 min-h-screen">
            <div className="max-w-7xl mx-auto">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}
