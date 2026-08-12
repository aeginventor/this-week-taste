import { site, type Channel } from "@/config/site";
import { formatPrice, formatWeek, type Item, type Week } from "@/lib/weeks";

function channelLabel(channel: string): string {
  return site.channels[channel as Channel] ?? channel;
}

function ItemCard({ item }: { item: Item }) {
  const price = formatPrice(item.price);
  return (
    <article className={`card ${item.status === "discontinued" ? "gone" : ""}`}>
      {item.image_url ? (
        // CLAUDE.md 7장: 이미지를 복제 저장하지 않고 원본 URL을 참조한다.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.image_url} alt="" className="thumb" loading="lazy" />
      ) : (
        <div className="thumb thumb-empty" aria-hidden="true" />
      )}
      <div className="card-body">
        <h3 className="name">{item.name}</h3>
        {item.blurb && <p className="blurb">{item.blurb}</p>}
        <p className="meta">
          <span className="brand">{item.brand}</span>
          {item.category && <span className="category">{item.category}</span>}
          {/* 가격은 채널에 따라 없는 것이 정상이다 (프랜차이즈 등). 없으면 아무것도 그리지 않는다. */}
          {price && <span className="price">{price}</span>}
        </p>
        {item.tags.length > 0 && (
          <p className="tags">
            {item.tags.map((tag) => (
              <span key={tag} className="tag">
                #{tag}
              </span>
            ))}
          </p>
        )}
        {item.source_url && (
          <a className="source" href={item.source_url} rel="nofollow noopener"
             target="_blank">
            원문 보기 ↗
          </a>
        )}
      </div>
    </article>
  );
}

export function WeekView({ data, weeks }: { data: Week; weeks: string[] }) {
  const active = data.items.filter((i) => i.status === "active");
  const discontinued = data.items.filter((i) => i.status === "discontinued");

  return (
    <div className="week">
      <div className="week-head">
        <h1>{formatWeek(data.week)} 신상</h1>
        <p className="counts">
          신상 {active.length}건
          {discontinued.length > 0 && ` · 단종 후보 ${discontinued.length}건`}
        </p>
        {weeks.length > 1 && (
          <nav className="archive">
            {weeks.map((w) => (
              <a key={w} href={`/week/${w}`}
                 className={w === data.week ? "current" : ""}>
                {formatWeek(w)}
              </a>
            ))}
          </nav>
        )}
      </div>

      {active.length === 0 ? (
        <p className="empty">이번 주에 새로 확인된 제품이 없습니다.</p>
      ) : (
        <section className="grid">
          {active.map((item) => (
            <ItemCard key={item.id} item={item} />
          ))}
        </section>
      )}

      {discontinued.length > 0 && (
        <section className="section">
          <h2>단종 후보</h2>
          <p className="note">
            지난주 목록에 있었으나 이번 주에 사라진 제품입니다. 실제 단종이
            아니라 일시 품절일 수 있습니다.
          </p>
          <div className="grid">
            {discontinued.map((item) => (
              <ItemCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      )}

      <p className="channels">
        {Array.from(new Set(data.items.map((i) => i.channel))).map((c) => (
          <span key={c}>{channelLabel(c)}</span>
        ))}
      </p>
    </div>
  );
}
