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

    API_KEY_CAPSOLVER
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://api.capsolver.com/',
    validateStatus: null,
    timeout: 20000,
    transformRequest: [
        data => {
            return typeof data === "object" ? {
                ...data,
                clientKey: API_KEY_CAPSOLVER,
            } : data;
        },
        ...axios.defaults.transformRequest
    ]
})

const generateCapsolverTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return {
                type: "ImageToTextTask",
                body: await filedata.readFile()
            };
        case "recaptchav2":
            return {
                type: "ReCaptchaV2Task",
                websiteURL: TARGET_URL_V2,
                websiteKey: RECAPTCHA_KEY_V2,
            };
        case "recaptchav2-invis":
            return {
                type: "ReCaptchaV2Task",
                websiteURL: TARGET_URL_V2_INVIS,
                websiteKey: RECAPTCHA_KEY_V2_INVIS,
                isInvisible: true,
            };
        case "recaptchav3":
        case "recaptchav3-enterprise":
            const isEnterprise = captcha === "recaptchav3-enterprise";
            return {
                type: isEnterprise ? "ReCaptchaV3EnterpriseTaskProxyLess" : "ReCaptchaV3TaskProxyLess",
                websiteURL: isEnterprise ? TARGET_URL_V3_ENTERPRISE : TARGET_URL_V3,
                websiteKey: isEnterprise ? RECAPTCHA_KEY_V3_ENTERPRISE : RECAPTCHA_KEY_V3,
                minScore: 0.5,
                pageAction: 'login',
            };
        case "cfturnstile":
            return {
                type: "AntiTurnstileTaskProxyLess",
                websiteURL: TARGET_URL_CF,
                websiteKey: SITE_KEY_CF
            };
        case "cfturnstile-invis":
            return {
                type: "AntiTurnstileTaskProxyLess",
                websiteURL: TARGET_URL_CF_INVIS,
                websiteKey: SITE_KEY_CF_INVIS
            };
        case "cfturnstile-non-interactive":
            return {
                type: "AntiTurnstileTaskProxyLess",
                websiteURL: TARGET_URL_CF_NON_INTERACTIVE,
                websiteKey: SITE_KEY_CF_NON_INTERACTIVE
            };
        default:
            throw new Error(`generateCapsolverTask: unsupported task type: ${captcha}`);
    }
};

const parseCapsolverSolution = (captcha, solution) => {
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
            throw new Error(`parseCapsolverSolution: unsupported task type: ${captcha}`);
    }
};

const makeReportCapsolverAccuracy = (taskObject, resultData) => async (_captcha, _taskId, success) => {
    const { data } = await api.post("/feedbackTask", {
        solved: success,
        task: taskObject,
        result: resultData,
    });

    if(data.errorId)
        throw new Error(`Could not report capsolver incorrect captcha: ${JSON.stringify(data)}`);
};

const doCapsolver = async (db, captcha, filedata) => {
    const createTaskTime = Date.now();
    const taskObject = await generateCapsolverTask(captcha, filedata);

    const { data: taskData, status: taskStatus } = await api.post("/createTask", {
        task: taskObject
    });

    if((taskStatus < 200 || taskStatus >= 300) || !taskData.taskId){
        console.error(`Could not create capsolver task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const { taskId } = taskData;
    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('capsolver', ?, ?, ?, ?)`, captcha, taskId, filedata?.filename ?? null, filedata?.expected ?? null);
    
    if(taskData.status === "ready"){
        return [
            solveId,
            true,
            taskStatus,
            JSON.stringify(taskData),
            'from_pipeline',
            createTaskTime,
            taskData.solution.createTime ?? Date.now(),
            parseCapsolverSolution(captcha, taskData.solution),
            makeReportCapsolverAccuracy(taskObject, taskData),
            taskId
        ];
    }

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
            console.error(`Capsolver task failed (status=${resultStatus})`, JSON.stringify(resultData));
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
                resultData.solution.createTime ?? Date.now(),
                parseCapsolverSolution(captcha, resultData.solution),
                makeReportCapsolverAccuracy(taskObject, resultData),
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doCapsolver
};