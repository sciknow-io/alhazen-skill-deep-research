import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "DisMech Notebook | Skillful-Alhazen",
  description: "Disease Mechanism Knowledge Graph",
};

export default function DisMechLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <>{children}</>;
}
