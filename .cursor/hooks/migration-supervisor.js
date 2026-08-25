const fs = require("fs");
const path = require("path");

const STATE_FILE = "migration-status.json";

function writeResponse(response) {
  process.stdout.write(`${JSON.stringify(response)}\n`);
}

function readPayload() {
  const raw = fs.readFileSync(0, "utf8").trim();
  return raw ? JSON.parse(raw) : {};
}

function readState() {
  const statePath = path.join(process.cwd(), STATE_FILE);
  const state = JSON.parse(fs.readFileSync(statePath, "utf8"));
  return { state, statePath };
}

function saveState(statePath, state, dryRun) {
  if (dryRun) {
    return;
  }
  const temporaryPath = `${statePath}.tmp`;
  fs.writeFileSync(
    temporaryPath,
    `${JSON.stringify(state, null, 2)}\n`,
    "utf8",
  );
  fs.renameSync(temporaryPath, statePath);
}

function currentStage(state) {
  return state.stages.find((stage) => stage.id === state.current_stage);
}

function addBlocker(state, message) {
  if (!Array.isArray(state.blockers)) {
    state.blockers = [];
  }
  if (!state.blockers.includes(message)) {
    state.blockers.push(message);
  }
}

function supervisorInstructions(stage, reason) {
  const checks = Array.isArray(stage.acceptance_checks)
    ? stage.acceptance_checks.map((check) => `- ${check}`).join("\n")
    : "- Проверки в состоянии этапа не заданы.";

  return [
    "Продолжи локальный цикл supervisor для миграции Python → C++.",
    `Причина продолжения: ${reason}.`,
    `Текущий этап: ${stage.id} — ${stage.title}.`,
    "",
    "Обязательно прочитай migration-status.json перед действиями.",
    "Не доверяй самоотчёту исполнителя: проверь изменённые файлы и фактический diff.",
    "Запусти независимого reviewer-подагента, затем выполни критерии приёмки:",
    checks,
    "",
    "Если все проверки прошли:",
    "1. Запиши evidence и accepted_at в текущий этап.",
    "2. Пометь этап completed, следующий pending-этап — in_progress.",
    "3. Обнови current_stage, общий status/progress_percent и blockers.",
    "4. Обнови Canvas cpp-migration-plan фактическими результатами.",
    "5. Запусти executor-подагента для следующего этапа с его executor_prompt.",
    "",
    "Если проверка не прошла, пометь этап blocked, запиши конкретный blocker и останови цикл.",
    "Не создавай commit и не выполняй push без отдельного запроса пользователя.",
  ].join("\n");
}

function startInstructions(stage) {
  return [
    "Продолжи локальный цикл supervisor для миграции Python → C++.",
    `Текущий этап: ${stage.id} — ${stage.title}.`,
    "",
    "Прочитай migration-status.json и проверь актуальный Git-статус.",
    "Если для этапа ещё нет завершённого executor-подагента, запусти generalPurpose executor.",
    `Задание исполнителю: ${stage.executor_prompt || stage.title}`,
    "Исполнитель должен изменить только файлы этапа, запустить релевантные проверки и вернуть список файлов и результаты.",
    "После завершения исполнителя не принимай этап по его самоотчёту: subagentStop вернёт задачу на независимую проверку.",
    "Не создавай commit и не выполняй push без отдельного запроса пользователя.",
  ].join("\n");
}

function handleSubagentStop(payload, state, statePath, stage, dryRun) {
  const status = payload.status || "error";
  state.last_subagent = {
    status,
    type: payload.subagent_type || null,
    description: payload.description || payload.task || null,
    summary: String(payload.summary || "").slice(0, 4000),
    modified_files: Array.isArray(payload.modified_files)
      ? payload.modified_files
      : [],
    completed_at: new Date().toISOString(),
  };
  state.updated_at = new Date().toISOString();

  if (status !== "completed") {
    stage.status = "blocked";
    state.status = "blocked";
    addBlocker(
      state,
      `Подагент этапа ${stage.id} завершился со статусом ${status}.`,
    );
    saveState(statePath, state, dryRun);
    return {};
  }

  stage.status = "review";
  state.status = "review";
  saveState(statePath, state, dryRun);
  return {
    followup_message: supervisorInstructions(
      stage,
      "executor-подагент завершил работу",
    ),
  };
}

function handleStop(payload, state, stage) {
  if ((payload.status || "completed") !== "completed") {
    return {};
  }
  if (["blocked", "paused", "completed"].includes(state.status)) {
    return {};
  }
  if (stage.status === "review") {
    return {
      followup_message: supervisorInstructions(
        stage,
        "supervisor остановился до завершения приёмки",
      ),
    };
  }
  if (stage.status === "in_progress") {
    return {
      followup_message: startInstructions(stage),
    };
  }
  return {};
}

function main() {
  const payload = readPayload();
  const { state, statePath } = readState();
  const dryRun = payload.dry_run === true;

  if (!state.automation || state.automation.enabled !== true) {
    writeResponse({});
    return;
  }

  const stage = currentStage(state);
  if (!stage) {
    state.status = "blocked";
    addBlocker(state, `Не найден текущий этап ${state.current_stage}.`);
    saveState(statePath, state, dryRun);
    writeResponse({});
    return;
  }

  const eventName = payload.hook_event_name;
  if (eventName === "subagentStop") {
    writeResponse(
      handleSubagentStop(payload, state, statePath, stage, dryRun),
    );
    return;
  }
  if (eventName === "stop") {
    writeResponse(handleStop(payload, state, stage));
    return;
  }
  writeResponse({});
}

try {
  main();
} catch (error) {
  console.error(`[migration-supervisor hook] ${error.stack || error}`);
  writeResponse({});
}
