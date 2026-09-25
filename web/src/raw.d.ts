/** Vite/Vitest가 `?raw`로 파일 내용을 문자열로 가져온다. 벤더 번들을 Node에서 실행하는 테스트가 쓴다. */
declare module "*?raw" {
  const content: string;
  export default content;
}
