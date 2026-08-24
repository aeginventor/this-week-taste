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
            제품 정보와 이미지는 각 브랜드 공식 사이트에서 가져왔습니다. 자세한
            내용은 각 항목의 원문 링크를 확인하세요.
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
