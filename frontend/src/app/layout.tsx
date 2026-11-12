'use client';

import { usePathname } from 'next/navigation';
import { Sidebar } from '@/components/layout/Sidebar';
import './globals.css';

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const pathname = usePathname();
  const isLoginPage = pathname === '/login';

  return (
    <html lang="en">
      <body className="bg-[#F7F9FC] text-[#172B4D] min-h-screen">
        {isLoginPage ? (
          <main className="min-h-screen">{children}</main>
        ) : (
          <div className="flex">
            <Sidebar />
            <main className="flex-1 ml-64 p-8 min-h-screen">
              <div className="max-w-7xl mx-auto">{children}</div>
            </main>
          </div>
        )}
      </body>
    </html>
  );
}
