/**
 * 표시용 서비스명은 여기 한 곳에서만 관리한다 (CLAUDE.md 서문).
 *
 * ⚠️ 서비스명은 아직 확정이 아니다. '이번주맛'은 플레이스홀더다.
 * 코드·폴더·변수명 어디에도 서비스명을 하드코딩하지 말 것.
 * 이름이 바뀌면 이 파일만 고치면 되어야 한다.
 */
export const site = {
  name: "이번주맛",
  tagline: "매주 새로 나온 식음료를 한자리에",
  description:
    "마트·편의점·카페·프랜차이즈의 신상 식음료를 매주 자동으로 모아 보여줍니다.",
  /**
   * 배포 주소. **크롤러 User-Agent가 이 주소의 /about을 가리킨다**(CLAUDE.md 5장).
   * 그래서 여기를 바꾸면 `THIS_WEEK_TASTE_UA` 환경변수도 같이 바꿔야 한다.
   * 두 값이 어긋나면 UA가 없는 페이지를 가리키게 되고, 그건 "연락 가능한 식별자"가 아니다.
   */
  url: "https://this-week-taste.vercel.app",
  /** 운영자 연락 창구. UA를 보고 찾아온 소스 사이트 운영자가 여기로 온다. */
  repo: "https://github.com/aeginventor/this-week-taste",
  /** 채널 코드 → 표시 이름 (CLAUDE.md 4장의 channel 값과 일치) */
  channels: {
    mart: "마트",
    convenience: "편의점",
    cafe: "카페",
    dessert: "디저트",
    restaurant: "음식점",
    fmcg: "식품",
  } as const,
} as const;

export type Channel = keyof typeof site.channels;
