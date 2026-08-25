"use client";

import { useMemo, useState } from "react";
import { site, type Channel } from "@/config/site";
import { ItemCard } from "@/components/ItemCard";
import type { Item } from "@/lib/item";

/**
 * 주차 항목의 필터와 검색 (CLAUDE.md 8장 6단계).
 *
 * 정적 내보내기(`output: export`)라 **전부 클라이언트에서 돈다.** 한 주차가
 * 수백 건 규모라 서버 인덱스가 필요 없다. 여기가 수천 건이 되는 날은
 * diff가 깨진 날이므로(8장 판단표), 그때 고칠 것은 이 컴포넌트가 아니다.
 *
 * 필터 상태를 URL 쿼리에 두지 않는 이유: 정적 페이지에서 `useSearchParams`를
 * 쓰면 그 페이지가 통째로 클라이언트 렌더링 경계로 밀려난다. 공유 링크가
 * 필터를 복원하는 것보다 첫 화면이 서버에서 오는 쪽이 낫다.
 */

type Facet = { value: string; label: string; count: number };

/** 값별 건수. 데이터에 실제로 있는 값만 칩이 된다 — 빈 칩은 클릭할 이유가 없다. */
function facets(items: Item[], pick: (i: Item) => string | null,
                label: (v: string) => string): Facet[] {
  const counts = new Map<string, number>();
  for (const item of items) {
    const value = pick(item);
    if (value) counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .map(([value, count]) => ({ value, label: label(value), count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));
}

function channelLabel(channel: string): string {
  // 채널 표시 이름의 단일 지점은 site.ts다 (CLAUDE.md 서문).
  return site.channels[channel as Channel] ?? channel;
}

function ChipRow({ title, options, selected, onToggle }: {
  title: string;
  options: Facet[];
  selected: Set<string>;
  onToggle: (value: string) => void;
}) {
  if (options.length < 2) return null;   // 고를 것이 하나뿐이면 필터가 아니다
  return (
    <div className="filter-row">
      <span className="filter-title">{title}</span>
      <div className="chips">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            className={`chip ${selected.has(option.value) ? "on" : ""}`}
            aria-pressed={selected.has(option.value)}
            onClick={() => onToggle(option.value)}
          >
            {option.label}
            <span className="chip-count">{option.count}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** 검색어 정규화 — 공백과 대소문자만 지운다. 한글이라 형태소 분석은 하지 않는다. */
function normalize(text: string): string {
  return text.toLowerCase().replace(/\s+/g, "");
}

export function FilteredItems({ items, discontinued }: {
  items: Item[];
  discontinued: Item[];
}) {
  const [channels, setChannels] = useState<Set<string>>(new Set());
  const [categories, setCategories] = useState<Set<string>>(new Set());
  const [brands, setBrands] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  // 칩은 **신상 기준**으로 만든다. 단종 후보까지 넣으면 이번 주에 없는 브랜드가
  // 칩으로 남아, 눌렀을 때 신상 0건이 나온다.
  const channelFacets = useMemo(
    () => facets(items, (i) => i.channel, channelLabel), [items]);
  const categoryFacets = useMemo(
    () => facets(items, (i) => i.category, (v) => v), [items]);
  const brandFacets = useMemo(
    () => facets(items, (i) => i.brand, (v) => v), [items]);

  const needle = normalize(query);
  const filter = useMemo(() => (list: Item[]) => list.filter((item) => {
    if (channels.size && !channels.has(item.channel)) return false;
    if (categories.size && !(item.category && categories.has(item.category))) return false;
    if (brands.size && !brands.has(item.brand)) return false;
    if (needle) {
      const haystack = normalize(`${item.name} ${item.blurb ?? ""}`);
      if (!haystack.includes(needle)) return false;
    }
    return true;
  }), [channels, categories, brands, needle]);

  const shownActive = filter(items);
  const shownGone = filter(discontinued);
  const active = channels.size + categories.size + brands.size + (query ? 1 : 0);

  function toggler(setter: (fn: (prev: Set<string>) => Set<string>) => void) {
    return (value: string) => setter((prev) => {
      const next = new Set(prev);
      if (!next.delete(value)) next.add(value);
      return next;
    });
  }

  function reset() {
    setChannels(new Set());
    setCategories(new Set());
    setBrands(new Set());
    setQuery("");
  }

  return (
    <>
      <section className="filters" aria-label="필터">
        <div className="filter-row">
          <span className="filter-title">검색</span>
          <input
            type="search"
            className="search"
            placeholder="제품 이름이나 설명"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          {active > 0 && (
            <button type="button" className="reset" onClick={reset}>
              초기화
            </button>
          )}
        </div>
        <ChipRow title="채널" options={channelFacets} selected={channels}
                 onToggle={toggler(setChannels)} />
        <ChipRow title="브랜드" options={brandFacets} selected={brands}
                 onToggle={toggler(setBrands)} />
        <ChipRow title="분류" options={categoryFacets} selected={categories}
                 onToggle={toggler(setCategories)} />
      </section>

      <p className="counts" aria-live="polite">
        신상 {shownActive.length}건
        {active > 0 && ` / 전체 ${items.length}건`}
        {shownGone.length > 0 && ` · 단종 후보 ${shownGone.length}건`}
      </p>

      {shownActive.length === 0 ? (
        // 빈 그리드를 조용히 내보내지 않는다 (2.4의 정신).
        <p className="empty">
          {active > 0
            ? "조건에 맞는 제품이 없습니다. 필터를 줄여보세요."
            : "이번 주에 새로 확인된 제품이 없습니다."}
        </p>
      ) : (
        <section className="grid">
          {shownActive.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>
      )}

      {shownGone.length > 0 && (
        <section className="section">
          <h2>단종 후보</h2>
          <p className="note">
            지난주 목록에 있었으나 이번 주에 사라진 제품입니다. 실제 단종이
            아니라 일시 품절일 수 있습니다.
          </p>
          <div className="grid">
            {shownGone.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}
    </>
  );
}
