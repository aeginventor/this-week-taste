import { formatPrice, type Item } from "@/lib/item";

/**
 * 항목 카드 하나. 서버·클라이언트 양쪽에서 쓴다.
 *
 * `WeekView`에서 떼어낸 이유: 필터가 클라이언트 컴포넌트라 카드도 거기서
 * 그려야 하는데, 두 벌로 만들면 한쪽만 고쳐지는 날이 온다.
 */
export function ItemCard({ item }: { item: Item }) {
  const price = formatPrice(item.price);
  return (
    <article className="card">
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
