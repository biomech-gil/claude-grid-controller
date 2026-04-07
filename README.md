# Claude Grid Controller

> Windows 데스크탑 사용자가 여러 개의 Claude Code CLI를 동시에 띄우고, 웹 브라우저에서 한눈에 관리할 수 있도록 만든 시스템입니다.

## 왜 만들었나

Claude Code CLI는 터미널 기반 도구입니다. 하나의 터미널에서 하나의 Claude와만 대화할 수 있죠. 그런데 여러 Claude를 동시에 띄워서 각각 다른 작업을 시키거나, 같은 명령을 한번에 보내고 싶은 경우가 있습니다.

문제는 **Windows에서는 tmux를 직접 쓸 수 없다**는 것입니다. tmux는 Linux 전용이기 때문에 WSL(Windows Subsystem for Linux)을 거쳐야 합니다. 이 과정에서 수많은 삽질을 거쳤고, 그 결과물이 이 프로젝트입니다.

### 이 시스템이 하는 일

```
[바탕화면 .bat 더블클릭]
    → [WSL Ubuntu 진입]
        → [tmux 세션 생성 + N개 패널 분할]
            → [각 패널에서 Claude Code CLI 자동 실행]
                → [웹 브라우저에서 전부 관리]
```

## 기능

| 기능 | 설명 |
|---|---|
| 자유 그리드 설정 | 시작 시 행x열 크기 지정 (예: 3x3 = 9개 Claude) |
| 개별 전송 | 각 노드 입력창에서 Enter |
| 다중 선택 전송 | 체크박스로 선택 후 일괄 전송 |
| 전체 전송 | 모든 노드에 동시 전송 |
| 실시간 모니터링 | 3초마다 각 노드의 출력 자동 갱신 |
| 프로젝트 저장 | 날짜_시간 폴더에 모든 통신 로그 자동 저장 |
| 세션 복원 | 이전 대화 기록을 새 세션에 전달하여 복원 |
| 기존 세션 연결 | 이미 실행 중인 tmux 세션에 바로 연결 |

## 요구사항

- Windows 10/11
- WSL (Ubuntu) — `wsl --install`로 설치
- Windows Terminal — 시작 메뉴에서 "터미널" 검색
- tmux — `sudo apt install tmux`
- Node.js — WSL 안에서 설치 필요
- Claude Code CLI — `npm install -g @anthropic-ai/claude-code`
- Python 3 — WSL Ubuntu에 기본 포함

## 설치

### 1단계: WSL 설치 (처음인 경우)

PowerShell을 **관리자 권한**으로 열고:

```powershell
wsl --install
```

재부팅 후 Ubuntu가 자동 설치됩니다. 사용자 이름과 비밀번호를 설정하세요.

### 2단계: WSL에 필요한 도구 설치

WSL 터미널 (시작 메뉴 → Ubuntu 또는 터미널에서 `wsl`)에서:

```bash
# tmux
sudo apt update && sudo apt install -y tmux

# Node.js
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
sudo apt install -y nodejs

# Claude Code
sudo npm install -g @anthropic-ai/claude-code
```

### 3단계: 프로젝트 클론

```bash
cd ~
git clone https://github.com/biomech-gil/claude-grid-controller.git
cd claude-grid-controller
```

### 4단계: Windows 바탕화면에 바로가기 생성

`Claude_Grid_Controller.bat` 파일을 바탕화면에 복사합니다. 내용:

```bat
@echo off
start wt wsl bash -c "cd ~/claude-grid-controller && echo '=== Claude Grid Controller ===' && echo '' && echo 'http://localhost:8080 으로 접속하세요' && echo '' && python3 server.py"
timeout /t 4 /nobreak >nul
start http://localhost:8080
```

> ⚠️ `wsl bash -c "..."` 형태를 쓸 때 bat 파일에서는 `start wt wsl bash ...`로 감싸야 합니다. `wt` 뒤에 직접 `-c`를 붙이면 Windows가 `-c`를 자체 플래그로 인식해서 오류가 납니다.

## 사용법

1. 바탕화면의 `Claude_Grid_Controller.bat` 더블클릭
2. 서버 터미널이 열리고, 4초 후 브라우저가 자동 실행
3. 브라우저에서:
   - 그리드 크기 설정 (행, 열)
   - **"새 프로젝트 시작"** → tmux 분할 + Claude 자동 실행 (약 25초 소요)
   - **"기존 세션 연결"** → 이미 실행 중인 세션에 바로 연결
4. 각 노드에 메시지 입력 후 Enter
5. 하단의 "전체 전송"이나 "선택 전송" 활용

## 프로젝트 구조

```
claude-grid-controller/
├── server.py                      # Python 백엔드 (표준 라이브러리만 사용)
├── index.html                     # 웹 프론트엔드 (순수 HTML/JS/CSS)
├── Claude_Grid_Controller.bat     # Windows 바탕화면 바로가기
├── README.md
├── .gitignore
└── projects/                      # 자동 생성 — 프로젝트 로그
    └── 20260408_015649/
        ├── config.json            # {rows, cols, created_at, pane_count}
        └── node_1.log             # [타임스탬프] INPUT/OUTPUT: 내용
```

## 아키텍처

```
┌──────────────┐     HTTP      ┌──────────────┐    tmux     ┌─────────────────┐
│  브라우저 UI  │ ←──────────→ │ Python 서버   │ ←────────→ │ Claude Code x N │
│  (index.html) │   :8080      │ (server.py)   │  send-keys  │ (tmux 패널들)    │
└──────────────┘               └──────────────┘  capture     └─────────────────┘
```

- 브라우저 → 서버: fetch API (JSON)
- 서버 → tmux: `tmux send-keys`로 입력 전달, `tmux capture-pane`으로 출력 수집
- 외부 의존성 없음 (Python 표준 라이브러리 + 순수 HTML/JS)

---

## ⚠️ 주의사항 & 삽질 기록

이 프로젝트를 만들면서 겪은 문제들입니다. 같은 실수를 반복하지 않도록 기록합니다.

### 1. tmux의 `-d` (detached) 모드에서 화면 분할이 안 된다

**증상**: `tmux new-session -d -s work` 후 `split-window`를 하면 패널이 1~5개밖에 안 생김

**원인**: detached 모드에서는 터미널 크기를 알 수 없어서, tmux가 분할할 공간이 부족하다고 판단합니다. `-x 300 -y 80` 같은 옵션을 줘도 불안정합니다.

**해결**: detached 모드를 쓰지 않고, 한 줄 명령으로 세션 생성과 분할을 동시에 합니다:

```bash
tmux new-session -s work \; \
  split-window \; select-layout tiled \; \
  split-window \; select-layout tiled \; \
  ...
```

서버에서는 이 명령을 임시 쉘 스크립트로 만들어서 실행합니다.

### 2. tmux base-index가 1인 경우 "can't find window: 0" 에러

**증상**: `tmux send-keys -t work:0.0 "hello" Enter` → `can't find window: 0`

**원인**: `~/.tmux.conf`에 `set -g base-index 1`과 `setw -g pane-base-index 1`이 설정되어 있으면, 윈도우와 패널 인덱스가 0이 아닌 **1부터** 시작합니다.

**해결**: 항상 `work:1.N` 형식을 사용합니다 (N은 1부터 시작).

```bash
# 확인 방법
tmux list-panes -t work -F '#{window_index}:#{pane_index}'
```

### 3. Ctrl+B가 안 먹히는 경우

**증상**: tmux 안에서 Ctrl+B → % 같은 단축키가 전혀 작동하지 않음

**원인 1**: `~/.tmux.conf`에서 prefix 키가 `Ctrl+A`로 변경되어 있었음
```
set -g prefix C-a
unbind C-b
```

**원인 2**: 일부 Windows 터미널이 Ctrl+B를 가로채는 경우

**해결**: 단축키 대신 명령어 직접 사용
```bash
tmux split-window -h   # Ctrl+B → % 대신
tmux split-window -v   # Ctrl+B → " 대신
```

### 4. Claude Code 신뢰 질문(Trust Prompt) 처리

**증상**: Claude Code 실행 시 "Is this a project you trust?" 선택 화면에서 `"2"` + Enter를 보내도 작동하지 않음

**원인**: 이 질문은 숫자 입력이 아니라 **선택형 UI**입니다. 기본 선택이 "Yes, I trust this folder"이므로 그냥 Enter만 보내면 됩니다.

**해결**:
```bash
# 틀린 방법
tmux send-keys -t work:1.1 "2" Enter

# 맞는 방법
tmux send-keys -t work:1.1 "" Enter
```

### 5. WSL 경로 변환 에러 ("Failed to translate")

**증상**: `wsl bash -c "..."` 실행 시 `wsl: Failed to translate 'Z:\...'` 경고

**원인**: 현재 디렉토리가 WSL에 매핑되지 않는 Windows 경로일 때 발생

**해결**: 무시해도 되는 경고입니다. 명령은 정상 실행됩니다. 또는 `cd C:/` 후 wsl 명령을 실행하면 경고가 줄어듭니다.

### 6. 5x5 (25개) 패널은 너무 작다

**증상**: 25개 패널을 분할하면 각 패널이 너무 작아서 글씨를 읽을 수 없음

**해결**: 실용적으로는 **3x3 (9개)** 또는 **2x3 (6개)** 정도가 적당합니다. 반드시 **Windows Terminal을 최대화**한 상태에서 실행하세요.

### 7. bat 파일에서 `wt` 뒤에 `-c` 플래그 사용 불가

**증상**: `wt wsl bash -c "..."` → `'-c'은(는) 내부 또는 외부 명령이 아닙니다`

**원인**: Windows Terminal(`wt`)이 `-c`를 자체 플래그로 해석

**해결**: 쉘 스크립트 파일을 만들어서 호출합니다:
```bat
@echo off
start wt wsl bash /mnt/c/Users/.../start.sh
```

### 8. nohup 백그라운드 프로세스가 tmux 세션 내에서 안 됨

**증상**: `nohup bash script.sh &`를 쓰면 스크립트가 실행되지 않거나 tmux 패널에 전달이 안 됨

**원인**: tmux 세션이 foreground로 attach되어 있으면, 백그라운드 프로세스의 tmux 명령이 타이밍 문제를 일으킴

**해결**: 서버의 백그라운드 스레드(Python threading)에서 tmux 명령을 보내는 방식으로 해결. bat 파일에서는 별도 프로세스로 서버를 시작하고, 서버가 모든 tmux 관리를 담당합니다.

### 9. 쉘 변수 이스케이프 문제

**증상**: `wsl bash -c` 안에서 `$변수`가 비어있거나 다른 값으로 치환됨

**원인**: Windows → WSL → bash를 거치면서 `$` 기호가 중간에 해석됨

**해결**: heredoc이나 별도 스크립트 파일을 사용합니다. 인라인 명령에서 변수를 쓸 때는 `\$`로 이스케이프합니다.

```bash
# 틀린 방법 (변수가 사라짐)
wsl bash -c "for i in $seq; do echo $i; done"

# 맞는 방법
wsl bash -c "for i in \$seq; do echo \$i; done"

# 가장 확실한 방법: 스크립트 파일로 분리
```

### 10. for 루프가 wsl bash -c 안에서 작동하지 않는 경우

**증상**: `wsl bash -c "for i in $(seq 1 24); do ... done"` 실행하면 루프가 안 돌거나 1회만 실행

**해결**: 스크립트를 파일로 저장한 뒤 실행합니다:
```bash
# script.sh 파일로 작성
wsl bash /mnt/c/Users/.../script.sh
```

---

## tmux 기본 사용법 (참고)

| 동작 | 명령어 |
|---|---|
| 새 세션 | `tmux` |
| 세션 목록 | `tmux ls` |
| 세션 연결 | `tmux attach` |
| 세션 종료 | `tmux kill-server` |
| 세로 분할 | `tmux split-window -h` |
| 가로 분할 | `tmux split-window -v` |
| 패널 이동 | `Alt+방향키` (설정된 경우) 또는 마우스 클릭 |
| 세션 분리 | `Ctrl+A → d` (prefix가 Ctrl+A인 경우) |

> tmux 창을 닫아도 세션은 살아있습니다. `tmux attach`로 다시 연결할 수 있습니다.

## License

MIT
