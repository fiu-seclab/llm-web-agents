// TODO: looks like nopecha's token APIs do not work..?

const axios = require('axios');
const {
    TARGET_URL_V2,
    RECAPTCHA_KEY_V2,
    TARGET_URL_V3,
    RECAPTCHA_KEY_V3,
    TARGET_URL_V3_ENTERPRISE,
    RECAPTCHA_KEY_V3_ENTERPRISE,
    TARGET_URL_CF,
    SITE_KEY_CF,

    API_KEY_NOPECHA
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://api.nopecha.com/',
    validateStatus: null,
    timeout: 20000,
    headers: {
        "Authorization": `Bearer ${API_KEY_NOPECHA}`
    }
})

const generateNopechaTask = (captcha) => {
    switch(captcha){
        case "recaptchav2":
            return {
                type: "recaptcha2",
                url: TARGET_URL_V2,
                sitekey: RECAPTCHA_KEY_V2,
                enterprise: false
            };
        case "recaptchav3":
        case "recaptchav3-enterprise":
            const isEnterprise = captcha === "recaptchav3-enterprise";
            return {
                type: "recaptcha3",
                url: isEnterprise ? TARGET_URL_V3_ENTERPRISE : TARGET_URL_V3,
                sitekey: isEnterprise ? RECAPTCHA_KEY_V3_ENTERPRISE : RECAPTCHA_KEY_V3,
                enterprise: isEnterprise,
                data: {
                    action: 'login'
                }
            };
        case "cfturnstile":
            return {
                type: "turnstile",
                url: TARGET_URL_CF,
                sitekey: SITE_KEY_CF
            }
        default:
            throw new Error(`generateCapsolverTask: unsupported task type: ${captcha}`);
    }
};

const doNopecha = async (db, captcha) => {
    const { data: taskData, status: taskStatus } = await api.post("/token", generateNopechaTask(captcha));

    if((taskStatus < 200 || taskStatus >= 300) || !taskData.data){
        console.error("DEBUG:", generateNopechaTask(captcha));
        console.error(`Could not create nopecha task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const createTaskTime = Date.now();

    const { data: taskId } = taskData;
    //const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id) VALUES ('nopecha', ?, ?)`, captcha, taskId);
    const solveId = 0;
    console.log("nopecha", captcha, taskId);

    await delay(2000);
    const startTime = Date.now();
    while(Date.now() - startTime < 180000){ // 2 minute timeout
        const { data: resultData, status: resultStatus } = await api.get("/token", {
            params: {
                id: taskId
            }
        });

        if(
            (resultStatus < 200 || resultStatus >= 300) && resultStatus !== 409
        ){
            console.error(`Nopecha task failed (status=${resultStatus})`, JSON.stringify(resultData));
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
                resultData.data,
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doNopecha
};