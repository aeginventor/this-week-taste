/**
 * 발행 항목의 타입과 표시용 포맷터.
 *
 * `weeks.ts`에서 떼어낸 이유: 그쪽은 `node:fs`로 파일을 읽는 **서버 전용**이라,
 * 클라이언트 컴포넌트(`FilteredItems`)가 거기서 타입 하나만 가져와도
 * webpack이 `node:fs`를 클라이언트 번들에 넣으려다 빌드가 깨진다.
 *
 * 여기에는 순수한 것만 둔다 — 타입, 문자열 포맷. 파일도 네트워크도 건드리지 않는다.
 *
 * 발행 항목 스키마는 CLAUDE.md 4장이 단일 진실 공급원이다.
 * 여기 타입이 그것과 어긋나면 CLAUDE.md 쪽이 맞다.
 */

export const WEEK_PATTERN = /^\d{4}-W\d{2}$/;

export type Item = {
  id: string;
  week: string;
  brand: string;
  channel: string;
  name: string;
  price: number | null;
  category: string | null;
  tags: string[];
  blurb: string | null;
  image_url: string | null;
  source_url: string | null;
  source_id: string;
  external_id: string;
  first_seen: string;
  last_seen: string;
  status: "active" | "discontinued";
};

export type Week = {
  week: string;
  generated_at: string;
  /** 이 주차에 발행된 소스들. 한 파일이 소스 여럿을 담는다. */
  sources: string[];
  counts: {
    total: number;
    active: number;
    discontinued: number;
    with_blurb: number;
  };
  items: Item[];
};

/** `2026-W33` → `2026년 33주차` */
export function formatWeek(week: string): string {
  const [year, w] = week.split("-W");
  return `${year}년 ${Number(w)}주차`;
}

export function formatPrice(price: number | null): string | null {
  return price === null ? null : `${price.toLocaleString("ko-KR")}원`;
}
