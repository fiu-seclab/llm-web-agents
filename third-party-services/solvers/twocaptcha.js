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
    TARGET_URL_HCAP_EASY,
    SITE_KEY_HCAP_EASY,
    TARGET_URL_HCAP,
    SITE_KEY_HCAP,
    TARGET_URL_CF,
    SITE_KEY_CF,
    TARGET_URL_CF_INVIS,
    SITE_KEY_CF_INVIS,
    TARGET_URL_CF_NON_INTERACTIVE,
    SITE_KEY_CF_NON_INTERACTIVE,

    API_KEY_2CAPTCHA,
    SOFTWARE_ID_2CAPTCHA,
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://api.2captcha.com/',
    validateStatus: null,
    timeout: 20000,
    transformRequest: [
        data => {
            return typeof data === "object" ? {
                ...data,
                clientKey: API_KEY_2CAPTCHA,
            } : data;
        },
        ...axios.defaults.transformRequest
    ]
})

const generate2CaptchaTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return {
                type: "ImageToTextTask",
                body: await filedata.readFile(),
                phrase: false,
                case: true,
                numeric: 0,
                math: false,
            }
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
                minScore: '0.7', // we want 0.5 minimum, but 2captcha only accepts 0.3, 0.7, 0.9
                pageAction: 'login',
                isEnterprise,
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
        case "hcaptcha-easy":
            return {
                type: "HCaptchaTaskProxyless",
                websiteURL: TARGET_URL_HCAP_EASY,
                websiteKey: SITE_KEY_HCAP_EASY
            };
        case "hcaptcha":
            return {
                type: "HCaptchaTaskProxyless",
                websiteURL: TARGET_URL_HCAP,
                websiteKey: SITE_KEY_HCAP
            };
        default:
            throw new Error(`generate2CaptchaTask: unsupported task type: ${captcha}`);
    }
};

const parse2CaptchaSolution = (captcha, solution) => {
    switch(captcha){
        case "textcaptcha":
            return solution.text;
        case "recaptchav2":
        case "recaptchav2-invis":
        case "recaptchav3":
        case "recaptchav3-enterprise":
        case "hcaptcha-easy":
        case "hcaptcha":
            return solution.gRecaptchaResponse;
        case "cfturnstile":
        case "cfturnstile-invis":
        case "cfturnstile-non-interactive":
            return solution.token;
        default:
            throw new Error(`parse2CaptchaSolution: unsupported task type: ${captcha}`);
    }
};

const report2CaptchaAccuracy = async (_captcha, taskId, success) => {
    const { data } = await api.post(success ? "/reportCorrect" : "/reportIncorrect", {
        taskId
    });

    if(data.errorId)
        throw new Error(`Could not report 2captcha incorrect captcha: ${JSON.stringify(data)}`);
};

const doTwoCaptcha = async (db, captcha, filedata) => {
    const { data: taskData, status: taskStatus } = await api.post("/createTask", {
        task: await generate2CaptchaTask(captcha, filedata)
    });

    if((taskStatus < 200 || taskStatus >= 300) || !taskData.taskId){
        console.error(`Could not create 2captcha task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const { taskId } = taskData;
    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('2captcha', ?, ?, ?, ?)`, captcha, taskId.toString(), filedata?.filename ?? null, filedata?.expected ?? null);
    
    await delay(2000);
    const startTime = Date.now();
    while(Date.now() - startTime < 120000){ // 2 minute timeout
        const { data: resultData, status: resultStatus } = await api.post("/getTaskResult", {
            taskId,
            softId: SOFTWARE_ID_2CAPTCHA
        });

        if(
            (resultStatus < 200 || resultStatus >= 300) || 
            resultData.errorId !== 0 ||
            !["processing", "ready"].includes(resultData.status)
        ){
            console.error(`2captcha task failed (status=${resultStatus})`, JSON.stringify(resultData));
            return [solveId, false, resultStatus, JSON.stringify(resultData), null, null, null, null];
        }

        if(resultData.status === "ready"){
            return [
                solveId,
                true,
                resultStatus,
                JSON.stringify(resultData),
                'from_solver',
                resultData.createTime * 1000,
                resultData.endTime * 1000,
                parse2CaptchaSolution(captcha, resultData.solution),
                report2CaptchaAccuracy,
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doTwoCaptcha
};