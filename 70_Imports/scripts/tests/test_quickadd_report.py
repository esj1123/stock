import json
from pathlib import Path
import shutil
import sys

import pytest

sys.path.append(str(Path(__file__).resolve().parents[3] / 'scripts'))

from quality_gate import run_command


def test_quickadd_report_schema_v2_uses_current_cli_markers():
    node = shutil.which("node") or shutil.which("node.exe")
    if node is None:
        pytest.skip("Node.js is required to execute the QuickAdd contract test")

    script_path = Path(__file__).resolve().parents[3] / "00_Config" / "QuickAdd" / "Stock_Command_Center.js"
    harness = r"""
const Module = require('module');
const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
  if (request === 'obsidian') {
    return { Notice: class Notice {}, normalizePath: value => value };
  }
  return originalLoad.call(this, request, parent, isMain);
};

const command = require(process.argv[1]);
const helpers = command.__test;
if (!helpers) throw new Error('QuickAdd test helpers are not exported');

function makeApp() {
  const writes = new Map();
  return {
    writes,
    app: {
      vault: {
        getAbstractFileByPath: () => null,
        createFolder: async () => {},
        create: async (filePath, content) => {
          writes.set(filePath, content);
          return { path: filePath };
        },
      },
    },
  };
}

(async () => {
  const stdout = [
    '[import] raw_files=4, parsed_rows=23, duplicate_removed=5, unclassified=2',
    '[qa] exceptions=7',
    '[done] no automated buy/sell orders were executed.',
  ].join('\n');
  const parsed = helpers.parseCounts(stdout);
  const partial = helpers.parseCounts('[qa] exceptions=3\n[done] complete');
  const successCapture = makeApp();
  const success = await helpers.createImportReport(successCapture.app, {
    mode: 'dry_run',
    start: new Date('2026-08-18T00:00:00Z'),
    end: new Date('2026-08-18T00:00:02Z'),
    result: { code: 0, stdout, stderr: '' },
  });
  const successContent = successCapture.writes.get(success.filePath);
  const noDone = await helpers.createImportReport(makeApp().app, {
    mode: 'dry_run',
    start: new Date('2026-08-18T00:00:00Z'),
    end: new Date('2026-08-18T00:00:01Z'),
    result: { code: 0, stdout: '[qa] exceptions=0', stderr: '' },
  });
  const badExit = await helpers.createImportReport(makeApp().app, {
    mode: 'dry_run',
    start: new Date('2026-08-18T00:00:00Z'),
    end: new Date('2026-08-18T00:00:01Z'),
    result: { code: 9, stdout: '[done] complete', stderr: '' },
  });
  process.stdout.write(JSON.stringify({
    parsed,
    partial,
    success: success.ok,
    reportChecks: {
      schemaVersion: successContent.includes('schema_version: 2'),
      successStatus: successContent.includes('status: "success"'),
      rawFiles: successContent.includes('raw_file_count: 4'),
      parsedRows: successContent.includes('parsed_row_count: 23'),
      duplicateRows: successContent.includes('duplicate_rows_removed_count: 5'),
      unclassifiedRows: successContent.includes('unclassified_row_count: 2'),
      qaExceptions: successContent.includes('qa_exception_count: 7'),
      legacyOmitted: ![
        'new_ledger_rows',
        'trade_notes_created',
        'cash_notes_created',
        'review_notes_created',
      ].some(field => successContent.includes(field)),
    },
    noDone: noDone.ok,
    badExit: badExit.ok,
  }));
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
"""
    code, output = run_command([node, "-e", harness, str(script_path)], script_path.parent)

    assert code == 0, output
    observed = json.loads(output)
    assert observed["parsed"] == {
        "rawFileCount": 4,
        "parsedRowCount": 23,
        "duplicateRowsRemovedCount": 5,
        "unclassifiedRowCount": 2,
        "qaExceptionCount": 7,
        "doneMarkerPresent": True,
    }
    assert observed["partial"] == {
        "rawFileCount": None,
        "parsedRowCount": None,
        "duplicateRowsRemovedCount": None,
        "unclassifiedRowCount": None,
        "qaExceptionCount": 3,
        "doneMarkerPresent": True,
    }
    assert observed["success"] is True
    assert observed["noDone"] is False
    assert observed["badExit"] is False

    assert all(observed["reportChecks"].values())
