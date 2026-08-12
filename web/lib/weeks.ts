/**
 * data/weeks/<week>.json 을 읽는다. 빌드 타임에만 호출된다 (정적 생성).
 *
 * 발행 항목 스키마는 CLAUDE.md 4장이 단일 진실 공급원이다.
 * 여기 타입이 그것과 어긋나면 CLAUDE.md 쪽이 맞다.
 */
import fs from "node:fs";
import path from "node:path";

export const WEEK_PATTERN = /^\d{4}-W\d{2}$/;

const WEEKS_DIR = path.join(process.cwd(), "..", "data", "weeks");

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
  external_id: string;
  first_seen: string;
  last_seen: string;
  status: "active" | "discontinued";
};

export type Week = {
  week: string;
  generated_at: string;
  counts: {
    total: number;
    active: number;
    discontinued: number;
    with_blurb: number;
  };
  items: Item[];
};

/** 발행된 주차 목록, 최신순. `.report.json` 같은 부산물은 제외한다. */
export function listWeeks(): string[] {
  if (!fs.existsSync(WEEKS_DIR)) return [];
  return fs
    .readdirSync(WEEKS_DIR)
    .filter((f) => f.endsWith(".json") && !f.endsWith(".report.json"))
    .map((f) => f.replace(/\.json$/, ""))
    .filter((w) => WEEK_PATTERN.test(w))
    .sort()
    .reverse();
}

export function readWeek(week: string): Week | null {
  if (!WEEK_PATTERN.test(week)) return null;
  const file = path.join(WEEKS_DIR, `${week}.json`);
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Week;
}

export function latestWeek(): string | null {
  return listWeeks()[0] ?? null;
}

/** `2026-W33` → `2026년 33주차` */
export function formatWeek(week: string): string {
  const [year, w] = week.split("-W");
  return `${year}년 ${Number(w)}주차`;
}

export function formatPrice(price: number | null): string | null {
  return price === null ? null : `${price.toLocaleString("ko-KR")}원`;
}
