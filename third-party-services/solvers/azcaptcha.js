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

    API_KEY_AZCAPTCHA,
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://azcaptcha.com/',
    validateStatus: null,
    timeout: 20000,
})

const generateAZCaptchaTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return {
                method: "base64",
                body: await filedata.readFile(),
                textinstructions: "case-sensitive"
            };
        case "recaptchav2":
            return {
                method: "userrecaptcha",
                googlekey: RECAPTCHA_KEY_V2,
                pageurl: TARGET_URL_V2
            };
        case "recaptchav2-invis":
            return {
                method: "userrecaptcha",
                googlekey: RECAPTCHA_KEY_V2_INVIS,
                pageurl: TARGET_URL_V2_INVIS,
                invisible: "1"
            };
        case "recaptchav3":
        case "recaptchav3-enterprise":
            const isEnterprise = captcha === "recaptchav3-enterprise";
            return {
                method: "userrecaptcha",
                version: "v3",
                pageurl: isEnterprise ? TARGET_URL_V3_ENTERPRISE : TARGET_URL_V3,
                googlekey: isEnterprise ? RECAPTCHA_KEY_V3_ENTERPRISE : RECAPTCHA_KEY_V3,
                min_score: '0.7', // we want 0.5 minimum, but 2captcha only accepts 0.3, 0.7, 0.9
                action: 'login',
            };
        default:
            throw new Error(`generateAZCaptchaTask: unsupported task type: ${captcha}`);
    }
};

const reportAZCaptchaAccuracy = async (_captcha, taskId, success) => {
    if(success)
        return;

    const { data } = await api.get("/res.php", {
        params: {
            key: API_KEY_AZCAPTCHA,
            action: "reportbad",
            id: taskId,
            json: 1
        }
    });

    if(data.status != 1 || data.request != "OK_REPORT_RECORDED")
        throw new Error(`Could not report azcaptcha correct/incorrect captcha: ${JSON.stringify(data)}`);
};

const doAZCaptcha = async (db, captcha, filedata) => {
    const { data: taskData, status: taskStatus } = await api.post("/in.php", new URLSearchParams({
        ...(await generateAZCaptchaTask(captcha, filedata)),
        key: API_KEY_AZCAPTCHA,
        json: "1"
    }).toString());

    if((taskStatus < 200 || taskStatus >= 300) || taskData.status != 1){
        console.error(`Could not create azcaptcha task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const createTaskTime = Date.now();

    const { request: taskId } = taskData;
    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('azcaptcha', ?, ?, ?, ?)`, captcha, taskId.toString(), filedata?.filename ?? null, filedata?.expected ?? null);

    await delay(2000);
    const startTime = Date.now();
    while(Date.now() - startTime < 240000){ // 4 minute timeout (azcaptcha is slow on recaptchav2!)
        const { data: resultData, status: resultStatus } = await api.get("/res.php", {
            params: {
                key: API_KEY_AZCAPTCHA,
                id: taskId,
                action: "get",
                taskinfo: "1",
                json: "1"
            }
        });

        if(
            (resultStatus < 200 || resultStatus >= 300) || 
            (resultData.status == 0 && resultData.request !== "CAPCHA_NOT_READY")
        ){
            console.error(`azcaptcha task failed (status=${resultStatus})`, JSON.stringify(resultData));
            return [solveId, false, resultStatus, JSON.stringify(resultData), null, null, null, null];
        }

        if(resultData.status == 1){
            return [
                solveId,
                true,
                resultStatus,
                JSON.stringify(resultData),
                'from_pipeline',
                createTaskTime,
                Date.now(),
                resultData.request,
                reportAZCaptchaAccuracy,
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doAZCaptcha
};