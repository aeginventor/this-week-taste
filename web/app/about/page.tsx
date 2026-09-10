import type { Metadata } from "next";
import { site } from "@/config/site";

export const metadata: Metadata = {
  title: `소개 — ${site.name}`,
  description: `${site.name}가 무엇을 어떻게 모으는지, 그리고 연락처.`,
};

/**
 * 크롤러 User-Agent가 가리키는 페이지다 (CLAUDE.md 5장).
 *
 * 소스 사이트 운영자가 서버 로그에서 우리 UA를 보고 찾아오는 곳이므로,
 * **무엇을 어떻게 수집하는지와 연락 방법이 반드시 있어야 한다.**
 * 이 페이지가 없으면 UA의 `+https://.../about`은 지키지 못할 약속이 된다.
 */
export default function AboutPage() {
  return (
    <article className="prose">
      <h1>{site.name} 소개</h1>
      <p>{site.description}</p>

      <h2>어떻게 모으나</h2>
      <p>
        각 브랜드 공식 사이트의 <strong>제품 목록</strong>을 매주 한 번 가져와,
        이전 목록과 비교합니다. 공식 안내와 공개된 신상품 소개 콘텐츠에서도 후보를 찾습니다.
      </p>
      <p>
        제품 정보와 출처, 과거에 소개된 상품을 대조해 이번 주 신상과 출시 예정 상품을
        정리합니다. 알 수 없는 출시일은 적지 않으며, 예정 일정은 원문 안내에 따라 달라질 수 있습니다.
      </p>

      <h2>수집할 때 지키는 것</h2>
      <ul>
        <li>
          <code>robots.txt</code>를 확인하고 막힌 경로는 요청하지 않습니다.
          차단된 경로는 우회하지 않고 다른 공개 경로를 확인합니다.
        </li>
        <li>
          요청은 <strong>1초에 한 번</strong>, 순차적으로만 보냅니다. 동시 요청은
          하지 않습니다.
        </li>
        <li>로그인이 필요한 페이지는 수집하지 않습니다.</li>
        <li>
          제품 정보를 그대로 옮기지 않습니다. <strong>한 줄 요약과 원문 링크</strong>만
          싣고, 자세한 내용은 각 브랜드 사이트에서 보도록 합니다.
        </li>
        <li>
          이미지는 <strong>복제하지 않고</strong> 각 브랜드 서버의 원본 주소를 그대로
          참조합니다.
        </li>
      </ul>

      <h2>연락</h2>
      <p>
        수집을 멈춰 달라는 요청, 잘못된 정보 신고, 그 밖의 문의는 저장소 이슈로
        남겨 주세요. 확인하는 대로 조치하겠습니다.
      </p>
      <p>
        <a href={`${site.repo}/issues`} rel="noopener">
          {site.repo.replace("https://", "")}/issues
        </a>
      </p>

      <h2>면책</h2>
      <p>
        이 사이트는 개인이 만든 비영리 프로젝트이며 소개된 브랜드와 아무 관계가
        없습니다. 가격과 판매 여부는 실제와 다를 수 있으니 반드시 원문을 확인하세요.
      </p>

      <p className="back">
        <a href="/">← 목록으로</a>
      </p>
    </article>
  );
}
