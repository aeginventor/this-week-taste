import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 정적 사이트로 내보낸다. data/weeks/*.json 은 빌드 타임에만 읽힌다.
  output: "export",
  // `week/2026-W33/index.html`로 내보낸다.
  // 이게 없으면 `week/2026-W33.html`이 되어, 확장자 없는 경로(/week/2026-W33)를
  // .html로 매핑해주는 호스트에서만 동작한다. 호스팅을 갈아탈 때마다 깨지는 종류의 문제라
  // 어디서든 되는 쪽으로 고정한다(python -m http.server, nginx, S3 포함).
  trailingSlash: true,
  images: {
    // CLAUDE.md 7장: 제품 이미지를 우리 서버에 복제 저장하지 않는다.
    // 원본 URL을 그대로 참조하므로 최적화(=우리 서버 경유)를 끈다.
    unoptimized: true,
  },
};

export default nextConfig;
