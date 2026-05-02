/**
 * Stock Command Center (QuickAdd)
 * - 하나의 QuickAdd Script로 Import/노트 생성/대시보드 열기까지 묶어서 실행
 * - 실행 결과를 '리포트 노트'로 남기고, 자동으로 열어줌
 *
 * 사용 방법
 * 1) Obsidian > Community plugins: QuickAdd 설치
 * 2) QuickAdd > Manage Macros > New Macro
 * 3) Choice: Script 선택 후, 이 파일(00_Config/QuickAdd/Stock_Command_Center.js) 지정
 * 4) Command palette에서 macro 실행
 */

const { Notice, normalizePath } = require('obsidian');
const path = require('path');
const { spawn } = require('child_process');

function getApp(params) {
  return params?.app ?? globalThis.app;
}

function getQA(params) {
  return params?.quickAddApi ?? params?.quickAddApi ?? null;
}

function nowStamp() {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return {
    yyyy, mm, dd, hh, mi, ss,
    date: `${yyyy}-${mm}-${dd}`,
    time: `${hh}:${mi}:${ss}`,
    yyyymm: `${yyyy}-${mm}`,
    yyyymmdd_hhmm: `${yyyy}-${mm}-${dd}_${hh}${mi}`,
    yyyymmdd_hhmmss: `${yyyy}-${mm}-${dd}_${hh}${mi}${ss}`,
  };
}

function getVaultBasePath(app) {
  const adapter = app?.vault?.adapter;
  if (!adapter) return null;
  if (typeof adapter.getBasePath === 'function') return adapter.getBasePath();
  if (typeof adapter.basePath === 'string') return adapter.basePath;
  return null;
}

async function ensureFolder(app, folderPath) {
  const p = normalizePath(folderPath);
  const existing = app.vault.getAbstractFileByPath(p);
  if (!existing) {
    await app.vault.createFolder(p);
  }
}

async function writeFile(app, filePath, content) {
  const p = normalizePath(filePath);
  const existing = app.vault.getAbstractFileByPath(p);
  if (!existing) {
    return await app.vault.create(p, content);
  }
  // TFile only
  await app.vault.modify(existing, content);
  return existing;
}

async function openPath(app, filePath, newLeaf = true) {
  const p = normalizePath(filePath);
  const file = app.vault.getAbstractFileByPath(p);
  if (!file) {
    new Notice(`파일을 찾을 수 없습니다: ${filePath}`);
    return;
  }
  const leaf = app.workspace.getLeaf(newLeaf);
  await leaf.openFile(file);
}

function spawnCapture(cmd, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { ...options, shell: false });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (d) => { stdout += d.toString(); });
    child.stderr.on('data', (d) => { stderr += d.toString(); });

    child.on('error', (err) => reject(err));
    child.on('close', (code) => {
      resolve({ code, stdout, stderr });
    });
  });
}

function parseCounts(text) {
  // 파서가 실패해도 리포트는 남기기
  const get = (re) => {
    const m = text.match(re);
    return m ? Number(m[1]) : null;
  };

  return {
    newLedgerRows: get(/신규\s*ledger\s*행\s*:\s*(\d+)/i),
    tradeNotes: get(/생성된\s*거래\s*노트\s*:\s*(\d+)/i),
    cashNotes: get(/생성된\s*입출금\s*노트\s*:\s*(\d+)/i),
    reviewNotes: get(/생성된\s*review\s*노트\s*:\s*(\d+)/i),
  };
}

function trimBlock(s, maxChars = 12000) {
  if (!s) return '';
  if (s.length <= maxChars) return s;
  return s.slice(0, maxChars) + `\n\n...(출력 길이 제한으로 일부 생략됨: ${s.length} chars)`;
}

async function runImport(app, { dryRun }) {
  const basePath = getVaultBasePath(app);
  if (!basePath) {
    throw new Error('Vault base path를 찾지 못했습니다. (모바일 환경이거나 파일 시스템 어댑터가 아닐 수 있음)');
  }

  const platform = process.platform;
  const args = dryRun ? ['--dry-run'] : [];

  if (platform === 'win32') {
    const ps1 = path.join(basePath, 'scripts', 'run_import.ps1');

    // 1차: windows powershell
    try {
      return await spawnCapture('powershell.exe', ['-ExecutionPolicy', 'Bypass', '-File', ps1, ...args], { cwd: basePath });
    } catch (e) {
      // 2차: PowerShell 7 (pwsh)
      if (String(e?.code) === 'ENOENT') {
        return await spawnCapture('pwsh', ['-ExecutionPolicy', 'Bypass', '-File', ps1, ...args], { cwd: basePath });
      }
      throw e;
    }
  }

  // macOS/Linux
  const sh = path.join(basePath, 'scripts', 'run_import.sh');
  return await spawnCapture('bash', [sh, ...args], { cwd: basePath });
}

async function createImportReport(app, { mode, start, end, result }) {
  const stamp = nowStamp();
  await ensureFolder(app, '70_Imports/logs');

  const ok = result.code === 0;
  const parsed = parseCounts(result.stdout + '\n' + result.stderr);

  const fileName = `Import_Run_${stamp.yyyymmdd_hhmm}.md`;
  const filePath = `70_Imports/logs/${fileName}`;

  const durationSec = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));

  const frontmatter = [
    '---',
    'doc_type: import_run',
    `run_at: "${stamp.date} ${stamp.time}"`,
    `mode: "${mode}"`,
    `status: "${ok ? 'success' : 'failed'}"`,
    parsed.newLedgerRows !== null ? `new_ledger_rows: ${parsed.newLedgerRows}` : 'new_ledger_rows: null',
    parsed.tradeNotes !== null ? `trade_notes_created: ${parsed.tradeNotes}` : 'trade_notes_created: null',
    parsed.cashNotes !== null ? `cash_notes_created: ${parsed.cashNotes}` : 'cash_notes_created: null',
    parsed.reviewNotes !== null ? `review_notes_created: ${parsed.reviewNotes}` : 'review_notes_created: null',
    `exit_code: ${result.code}`,
    '---',
  ].join('\n');

  const body = [
    `# Import 실행 리포트 - ${stamp.date} ${stamp.hh}:${stamp.mi}`,
    '',
    '## 요약',
    `- 실행 모드: ${mode}`,
    `- 결과: ${ok ? '성공' : '실패'}`,
    `- 소요 시간: ${durationSec}초`,
    parsed.newLedgerRows !== null ? `- 신규 ledger 행: ${parsed.newLedgerRows}` : '- 신규 ledger 행: (파싱 실패)',
    parsed.tradeNotes !== null ? `- 생성된 거래 노트: ${parsed.tradeNotes}` : '- 생성된 거래 노트: (파싱 실패)',
    parsed.cashNotes !== null ? `- 생성된 입출금 노트: ${parsed.cashNotes}` : '- 생성된 입출금 노트: (파싱 실패)',
    parsed.reviewNotes !== null ? `- 생성된 review 노트: ${parsed.reviewNotes}` : '- 생성된 review 노트: (파싱 실패)',
    '',
    '## 다음 액션(클릭)',
    '- [[10_Dashboard/Import_Review|Import 점검(UNCLASSIFIED/누락 확인)]]',
    '- [[10_Dashboard/Portfolio|포트폴리오]]',
    '- [[10_Dashboard/Start_Here|Start Here]]',
    '',
    '## stdout',
    '```text',
    trimBlock(result.stdout),
    '```',
    '',
    '## stderr',
    '```text',
    trimBlock(result.stderr),
    '```',
    '',
    '---',
    '### 참고',
    '- raw 엑셀은 수정하지 말고 `70_Imports/raw/`에 그대로 두는 것을 권장합니다.',
  ].join('\n');

  const content = `${frontmatter}\n\n${body}\n`;

  await writeFile(app, filePath, content);
  return { filePath, ok, parsed };
}

async function createMonthEndSnapshot(app) {
  const stamp = nowStamp();
  const templatePath = '99_Templates/Month_End_Snapshot.md';
  const tplFile = app.vault.getAbstractFileByPath(normalizePath(templatePath));
  if (!tplFile) {
    throw new Error(`템플릿 파일을 찾지 못했습니다: ${templatePath}`);
  }
  const tpl = await app.vault.read(tplFile);
  const filled = tpl
    .replaceAll('YYYY-MM-DD', stamp.date)
    .replaceAll('YYYY-MM', stamp.yyyymm);

  const filePath = `50_Journal/${stamp.yyyymm}_Month_End_Snapshot.md`;
  const existing = app.vault.getAbstractFileByPath(normalizePath(filePath));
  if (existing) {
    // 이미 있으면 열기만
    await openPath(app, filePath, true);
    new Notice(`D 생성 완료(이미 존재): ${filePath}`);
    return;
  }

  await writeFile(app, filePath, filled);
  await openPath(app, filePath, true);
  new Notice(`D 생성 완료: ${filePath}`);
}

async function createCompanyFolder(app, qa) {
  const ticker = (await qa.inputPrompt('티커/종목코드를 입력하세요 (예: 005930 또는 AAPL)')).trim();
  if (!ticker) {
    new Notice('취소됨');
    return;
  }
  const name = (await qa.inputPrompt('회사명을 입력하세요(표시용)')).trim();

  const folder = `20_Companies/${ticker}`;
  await ensureFolder(app, folder);
  await ensureFolder(app, `${folder}/Notes`);
  await ensureFolder(app, `${folder}/Events`);

  const companyPath = `${folder}/Company.md`;
  const existing = app.vault.getAbstractFileByPath(normalizePath(companyPath));
  if (existing) {
    await openPath(app, companyPath, true);
    new Notice(`C 생성 완료(이미 존재): ${ticker}`);
    return;
  }

  const templatePath = '99_Templates/Company.md';
  const tplFile = app.vault.getAbstractFileByPath(normalizePath(templatePath));
  if (!tplFile) {
    throw new Error(`템플릿 파일을 찾지 못했습니다: ${templatePath}`);
  }

  const stamp = nowStamp();
  let tpl = await app.vault.read(tplFile);

  tpl = tpl
    .replace('ticker: "TICKER"', `ticker: "${ticker}"`)
    .replace('name: "회사명"', `name: "${name || '회사명'}"`)
    .replace(/last_update:\s*\d{4}-\d{2}-\d{2}/, `last_update: ${stamp.date}`)
    .replace(/price_date:\s*\d{4}-\d{2}-\d{2}/, `price_date: ${stamp.date}`)
    .replaceAll('{{ticker}}', ticker)
    .replaceAll('{{name}}', name || '회사명');

  await writeFile(app, companyPath, tpl);
  await openPath(app, companyPath, true);
  new Notice(`C 생성 완료: ${ticker}`);
}

async function openStartHere(app) {
  await openPath(app, '10_Dashboard/Start_Here.md', true);
  new Notice('E 열기 완료: Start_Here');
}

module.exports = async (params) => {
  const app = getApp(params);
  const qa = getQA(params);

  if (!app) {
    throw new Error('Obsidian app 객체를 찾지 못했습니다.');
  }

  if (!qa) {
    new Notice('QuickAdd API를 찾지 못했습니다. QuickAdd에서 Script로 실행했는지 확인하세요.');
    return;
  }

  const actions = [
    { label: 'A) Import 실행 + 리포트 생성 + 대시보드 열기(추천)', value: 'import_full' },
    { label: 'B) Import 테스트(dry-run) + 리포트 생성', value: 'import_dry' },
    { label: 'C) 새 기업 폴더 생성(템플릿)', value: 'create_company' },
    { label: 'D) 월말 스냅샷 노트 생성', value: 'month_end' },
    { label: 'E) Start_Here 열기(바로가기)', value: 'open_start' },
  ];

  const choice = await qa.suggester(actions.map(a => a.label), actions.map(a => a.value));
  if (!choice) return;

  try {
    if (choice === 'import_full' || choice === 'import_dry') {
      const isDry = choice === 'import_dry';
      new Notice(`${isDry ? 'B' : 'A'} 실행 시작: Import`);

      const start = new Date();
      const result = await runImport(app, { dryRun: isDry });
      const end = new Date();

      const report = await createImportReport(app, {
        mode: isDry ? 'dry_run' : 'full',
        start,
        end,
        result,
      });

      await openPath(app, report.filePath, true);

      // import_full이면 Import_Review도 같이 열기
      if (!isDry) {
        await openPath(app, '10_Dashboard/Import_Review.md', true);
      }

      const t = report.parsed.tradeNotes ?? '?';
      const c = report.parsed.cashNotes ?? '?';
      const r = report.parsed.reviewNotes ?? '?';

      new Notice(`✅ ${(isDry ? 'B' : 'A')} 생성 완료: 거래 ${t}, 입출금 ${c}, review ${r}`);
      return;
    }

    if (choice === 'create_company') {
      await createCompanyFolder(app, qa);
      return;
    }

    if (choice === 'month_end') {
      await createMonthEndSnapshot(app);
      return;
    }

    if (choice === 'open_start') {
      await openStartHere(app);
      return;
    }

  } catch (e) {
    const msg = e?.message ? String(e.message) : String(e);
    console.error(e);
    new Notice(`오류: ${msg}`);

    // 에러 리포트를 남겨두면 디버깅이 쉬움
    try {
      const stamp = nowStamp();
      await ensureFolder(app, '70_Imports/logs');
      const fp = `70_Imports/logs/ERROR_${stamp.yyyymmdd_hhmmss}.md`;
      const content = [
        '---',
        'doc_type: error_log',
        `run_at: "${stamp.date} ${stamp.time}"`,
        `message: "${msg.replaceAll('"', '\\"')}"`,
        '---',
        '',
        `# 오류 로그 - ${stamp.date} ${stamp.hh}:${stamp.mi}:${stamp.ss}`,
        '',
        '## 오류 메시지',
        msg,
        '',
        '## 점검 포인트',
        '- QuickAdd가 설치/활성화되어 있는지',
        '- Python/venv가 정상인지',
        '- `scripts/run_import.*` 파일이 Vault에 존재하는지',
        '- Windows면 PowerShell 실행 정책(ExecutionPolicy) 제한이 있는지',
        '',
        '## 링크',
        '- [[00_Config/Setup_Checklist|Setup Checklist]]',
        '- [[00_Config/QuickStart|QuickStart]]',
      ].join('\n');

      await writeFile(app, fp, content);
      await openPath(app, fp, true);
    } catch (_) {
      // ignore
    }
  }
};
