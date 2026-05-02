# QuickAdd 자동화(커맨드 센터)

이 폴더는 **QuickAdd 한 개 매크로(=버튼)**로
- Import 실행
- 실행 리포트 생성
- 대시보드 열기
같은 반복 작업을 한 번에 처리하기 위한 설정 파일을 모아둔 곳입니다.

## 1) 필요한 플러그인
- QuickAdd (필수)
- Dataview (필수: 대시보드 렌더링)

## 2) 한 번만 설정(추천)
1) Settings → Community plugins → **QuickAdd 설치/활성화**
2) QuickAdd → **Manage Macros** → New Macro
3) Choice 추가 → **Script** 선택
4) Script 파일 경로 지정:
   - `00_Config/QuickAdd/Stock_Command_Center.js`
5) 매크로 이름 예시:
   - `Stock Command Center`

## 3) 사용 방법
- Command palette에서 위 매크로를 실행하면 메뉴가 뜹니다.
- Import를 실행하면 결과가 `70_Imports/logs/` 아래에 리포트 노트로 저장되고, 자동으로 열립니다.

## 4) 산출물(예)
- `70_Imports/logs/Import_Run_YYYY-MM-DD_HHMM.md`
- 실패 시: `70_Imports/logs/ERROR_YYYY-MM-DD_HHMMSS.md`

> 이 기능은 PC(데스크탑)에서 외부 명령(Python/PowerShell/bash)을 실행하기 때문에,
> 모바일 환경에서는 Import 실행이 제한될 수 있습니다.
