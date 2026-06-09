const axios = require('axios');
const {
    TARGET_URL_V2,
    RECAPTCHA_KEY_V2,
    TARGET_URL_V2_INVIS,
    RECAPTCHA_KEY_V2_INVIS,
    TARGET_URL_V3,
    RECAPTCHA_KEY_V3,
    TARGET_URL_V3_ENTERPRISE,
    RECAPTCHA_KEY_V3_ENTERPRISE,
    TARGET_URL_CF,
    SITE_KEY_CF,
    TARGET_URL_CF_INVIS,
    SITE_KEY_CF_INVIS,
    TARGET_URL_CF_NON_INTERACTIVE,
    SITE_KEY_CF_NON_INTERACTIVE,

    API_KEY_CAPMONSTER,
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://api.capmonster.cloud',
    validateStatus: null,
    timeout: 20000,
    transformRequest: [
        data => {
            return typeof data === "object" ? {
                ...data,
                clientKey: API_KEY_CAPMONSTER,
            } : data;
        },
        ...axios.defaults.transformRequest
    ]
})

const generateCapmonsterTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return {
                type: "ImageToTextTask",
                body: await filedata.readFile(),
                case: true,
                numeric: 0
            };
        case "recaptchav2":
            return {
                type: "RecaptchaV2TaskProxyless",
                websiteURL: TARGET_URL_V2,
                websiteKey: RECAPTCHA_KEY_V2,
            };
        case "recaptchav2-invis":
            return {
                type: "RecaptchaV2TaskProxyless",
                websiteURL: TARGET_URL_V2_INVIS,
                websiteKey: RECAPTCHA_KEY_V2_INVIS,
                isInvisible: true,
            };
        case "recaptchav3":
        case "recaptchav3-enterprise":
            const isEnterprise = captcha === "recaptchav3-enterprise";
            return {
                type: "RecaptchaV3TaskProxyless",
                websiteURL: isEnterprise ? TARGET_URL_V3_ENTERPRISE : TARGET_URL_V3,
                websiteKey: isEnterprise ? RECAPTCHA_KEY_V3_ENTERPRISE : RECAPTCHA_KEY_V3,
                minScore: 0.5,
                pageAction: 'login',
            };
        case "cfturnstile":
            return {
                type: "TurnstileTaskProxyless",
                websiteURL: TARGET_URL_CF,
                websiteKey: SITE_KEY_CF
            };
        case "cfturnstile-invis":
            return {
                type: "TurnstileTaskProxyless",
                websiteURL: TARGET_URL_CF_INVIS,
                websiteKey: SITE_KEY_CF_INVIS
            };
        case "cfturnstile-non-interactive":
            return {
                type: "TurnstileTaskProxyless",
                websiteURL: TARGET_URL_CF_NON_INTERACTIVE,
                websiteKey: SITE_KEY_CF_NON_INTERACTIVE
            };
        default:
            throw new Error(`generateCapmonsterTask: unsupported task type: ${captcha}`);
    }
};

const parseCapmonsterSolution = (captcha, solution) => {
    switch(captcha){
        case "textcaptcha":
            return solution.text;
        case "recaptchav2":
        case "recaptchav2-invis":
        case "recaptchav3":
        case "recaptchav3-enterprise":
            return solution.gRecaptchaResponse;
        case "cfturnstile":
        case "cfturnstile-invis":
        case "cfturnstile-non-interactive":
            return solution.token;
        default:
            throw new Error(`parseCapmonsterSolution: unsupported task type: ${captcha}`);
    }
};

const reportCapmonsterAccuracy = async (captcha, taskId, success) => {
    // no need to report correctly solved captchas
    if(success)
        return;

    switch(captcha){
        case "recaptchav2":
        case "recaptchav2-invis":
        case "recaptchav3":
        case "recaptchav3-enterprise":
        case "cfturnstile":
        case "cfturnstile-invis":
        case "cfturnstile-non-interactive": {
            const { data } = await api.post("/reportIncorrectTokenCaptcha", {
                taskId
            });

            if(data.errorId)
                throw new Error(`Could not report capmonster.cloud incorrect captcha (taskId=${taskId}): ${JSON.stringify(data)}`);
        }
    }
};

const doCapmonster = async (db, captcha, filedata) => {
    const { data: taskData, status: taskStatus, config } = await api.post("/createTask", {
        task: await generateCapmonsterTask(captcha, filedata)
    });

    if((taskStatus < 200 || taskStatus >= 300) || !taskData.taskId){
        console.log("DEBUG:", generateCapmonsterTask(captcha), taskData, config.data);
        console.error(`Could not create capmonster task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const createTaskTime = Date.now();

    const { taskId } = taskData;
    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('capmonster', ?, ?, ?, ?)`, captcha, taskId, filedata?.filename ?? null, filedata?.expected ?? null);
    
    await delay(2000);
    const startTime = Date.now();
    while(Date.now() - startTime < 120000){ // 2 minute timeout
        const { data: resultData, status: resultStatus } = await api.post("/getTaskResult", {
            taskId,
        });

        if(
            (resultStatus < 200 || resultStatus >= 300) || 
            resultData.errorId !== 0 ||
            !["processing", "ready"].includes(resultData.status)
        ){
            console.error(`Capmonster task failed (status=${resultStatus})`, JSON.stringify(resultData));
            return [solveId, false, resultStatus, JSON.stringify(resultData), null, null, null, null];
        }

        if(resultData.status === "ready"){
            return [
                solveId,
                true,
                resultStatus,
                JSON.stringify(resultData),
                'from_pipeline',
                createTaskTime,
                Date.now(),
                parseCapmonsterSolution(captcha, resultData.solution),
                reportCapmonsterAccuracy,
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doCapmonster
};