import type { Metadata } from "next";
import { site } from "@/config/site";
import "./globals.css";

export const metadata: Metadata = {
  title: site.name,
  description: site.description,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        <header className="header">
          <a href="/" className="brand">
            {site.name}
          </a>
          <p className="tagline">{site.tagline}</p>
        </header>
        <main>{children}</main>
        <footer className="footer">
          <p>
            상품 정보는 각 항목에 연결된 출처를 바탕으로 소개합니다.
            자세한 내용과 최신 판매 정보는 원문 링크를 확인하세요.
          </p>
          <p>
            {/* 크롤러 UA가 이 경로를 가리킨다. 링크가 없으면 아무도 못 찾는다. */}
            <a href="/about">소개 · 수집 방식 · 연락처</a>
          </p>
        </footer>
      </body>
    </html>
  );
}
