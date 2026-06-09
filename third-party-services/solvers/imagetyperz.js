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
    TARGET_URL_HCAP_EASY,
    SITE_KEY_HCAP_EASY,
    TARGET_URL_HCAP,
    SITE_KEY_HCAP,

    API_KEY_IMAGETYPERZ,
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://www.captchatypers.com',
    validateStatus: null,
    timeout: 20000,
})

const generateImageTyperzTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return [
                "/Forms/UploadFileAndGetTextNEWToken.ashx",
                {
                    file: await filedata.readFile(),
                    action: "UPLOADCAPTCHA",
                    iscase: "true"
                }
            ]
        case "recaptchav2":
            return [
                "/captchaapi/UploadRecaptchaToken.ashx",
                {
                    pageurl: TARGET_URL_V2,
                    googlekey: RECAPTCHA_KEY_V2,
                    action: "UPLOADCAPTCHA",
                    recaptchatype: "1", // can be one of this 3 values: 1 - normal, 2 - invisible, 3 - v3
                }
            ];
        case "recaptchav2-invis":
            return [
                "/captchaapi/UploadRecaptchaToken.ashx",
                {
                    pageurl: TARGET_URL_V2_INVIS,
                    googlekey: RECAPTCHA_KEY_V2_INVIS,
                    action: "UPLOADCAPTCHA",
                    recaptchatype: "2", // 2 = invisible
                }
            ];
        case "recaptchav3":
            return [
                "/captchaapi/UploadRecaptchaToken.ashx",
                {
                    pageurl: TARGET_URL_V3,
                    googlekey: RECAPTCHA_KEY_V3,
                    action: "UPLOADCAPTCHA",
                    recaptchatype: "3", // can be one of this 3 values: 1 - normal, 2 - invisible, 3 - v3
                    captchaaction: "login",
                    score: "0.7",
                }
            ];
        case "recaptchav3-enterprise":
            return [
                "/captchaapi/UploadRecaptchaEnt.ashx",
                {
                    pageurl: TARGET_URL_V3_ENTERPRISE,
                    googlekey: RECAPTCHA_KEY_V3_ENTERPRISE,
                    action: "UPLOADCAPTCHA",
                    enterprise_type: "v3",
                    captchaaction: "login",
                    score: "0.7",
                }
            ];
        case "cfturnstile":
            return [
                "/captchaapi/Uploadturnstile.ashx",
                {
                    pageurl: TARGET_URL_CF,
                    sitekey: SITE_KEY_CF,
                    action: "UPLOADCAPTCHA"
                }
            ];
        case "cfturnstile-invis":
            return [
                "/captchaapi/Uploadturnstile.ashx",
                {
                    pageurl: TARGET_URL_CF_INVIS,
                    sitekey: SITE_KEY_CF_INVIS,
                    action: "UPLOADCAPTCHA"
                }
            ];
        case "cfturnstile-non-interactive":
            return [
                "/captchaapi/Uploadturnstile.ashx",
                {
                    pageurl: TARGET_URL_CF_NON_INTERACTIVE,
                    sitekey: SITE_KEY_CF_NON_INTERACTIVE,
                    action: "UPLOADCAPTCHA"
                }
            ];
        case "hcaptcha-easy":
            return [
                "/captchaapi/UploadHCaptchaUser.ashx",
                {
                    pageurl: TARGET_URL_HCAP_EASY,
                    sitekey: SITE_KEY_HCAP_EASY,
                    action: "UPLOADCAPTCHA"
                }
            ];
        case "hcaptcha":
            return [
                "/captchaapi/UploadHCaptchaUser.ashx",
                {
                    pageurl: TARGET_URL_HCAP,
                    sitekey: SITE_KEY_HCAP,
                    action: "UPLOADCAPTCHA"
                }
            ];
        default:
            throw new Error(`generateImageTyperzTask: unsupported task type: ${captcha}`);
    }
};

const reportImageTyperzAccuracy = async (_captcha, taskId, success) => {
    if(success)
        return;

    await api.post("/Forms/SetBadImageToken.ashx", new URLSearchParams({
        token: API_KEY_IMAGETYPERZ,
        imageid: taskId,
        action: "SETBADIMAGE"
    }).toString(), {
        validateStatus: status => status >= 200 && status < 300
    });
};

const doImageTyperz = async (db, captcha, filedata) => {
    const [url, data] = await generateImageTyperzTask(captcha, filedata);
    const createTaskTime = Date.now();

    const { data: taskData, status: taskStatus } = await api.post(url, new URLSearchParams({
        ...data,
        token: API_KEY_IMAGETYPERZ
    }).toString(), {
        responseType: "text",

        // image captchas are synchronously returned
        ...(captcha === "textcaptcha" ? {
            timeout: 180000
        } : {})
    });

    if(taskStatus < 200 || taskStatus >= 300){
        console.error(`Could not create imagetyperz task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    // resp can be "`OK|12345678`, `12345678`, or `[{"CaptchaId": "12345678"}]`, or "12345678|SOLUTION"
    let taskId;
    let parts = taskData.split("|");
    if(captcha === "textcaptcha"){
        taskId = parts[0];
    }else{
        parts = JSON.parse(parts.length >= 2 ? parts[1] : parts[0]);
        taskId = (typeof parts === "object" ? parts[0].CaptchaId : parts).toString();
    }

    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('imagetyperz', ?, ?, ?, ?)`, captcha, taskId, filedata?.filename ?? null, filedata?.expected ?? null);

    // image captchas are synchronously returned
    if(captcha === "textcaptcha"){
        if(parts[1]){ // has solution
            return [
                solveId,
                true,
                taskStatus,
                JSON.stringify(taskData),
                'from_pipeline',
                createTaskTime,
                Date.now(),
                parts[1],
                reportImageTyperzAccuracy,
                taskId
            ];
        }
    }else{
        await delay(2000);
    }

    const startTime = Date.now();
    while(Date.now() - startTime < 120000){ // 2 minute timeout
        const { data: resultData, status: resultStatus } = await api.get("/captchaapi/GetCaptchaResponseJson.ashx", {
            params: {
                token: API_KEY_IMAGETYPERZ,
                captchaid: taskId,
                action: "GETTEXT"
            }
        });

        const response = resultData[0];
        if(
            (resultStatus < 200 || resultStatus >= 300) || 
            !["Pending", "Solved"].includes(response.Status)
        ){
            console.error(`Imagetyperz task failed (status=${resultStatus})`, JSON.stringify(resultData));
            return [solveId, false, resultStatus, JSON.stringify(resultData), null, null, null, null];
        }

        if(response.Status === "Solved"){
            return [
                solveId,
                true,
                resultStatus,
                JSON.stringify(resultData),
                'from_pipeline',
                createTaskTime,
                Date.now(),
                response.Response,
                reportImageTyperzAccuracy,
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doImageTyperz
};