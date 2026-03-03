import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Islam Intelligent'
}

export default function RootLayout({
  children
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" dir="ltr">
      <body className="antialiased">{children}</body>
    </html>
  )
}
