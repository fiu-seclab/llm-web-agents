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

    API_KEY_BESTCAPTCHA,
} = require('../constants');
const {
    delay
} = require('../util');

const api = axios.create({
    baseURL: 'https://bcsapi.xyz/api',
    validateStatus: null,
    timeout: 20000,
    transitional: {
        clarifyTimeoutError: true
    }
})

const generateBestCaptchaTask = async (captcha, filedata) => {
    switch(captcha){
        case "textcaptcha":
            return [
                "/captcha/image",
                {
                    b64image: await filedata.readFile(),
                    is_case: 1
                }
            ]
        case "recaptchav2":
            return [
                "/captcha/recaptcha",
                {
                    page_url: TARGET_URL_V2,
                    site_key: RECAPTCHA_KEY_V2,
                    type: "1", // 1 = v2
                }
            ];
        case "recaptchav2-invis":
            return [
                "/captcha/recaptcha",
                {
                    page_url: TARGET_URL_V2_INVIS,
                    site_key: RECAPTCHA_KEY_V2_INVIS,
                    type: "2", // 2 = invisible v2
                }
            ];
        case "recaptchav3":
            return [
                "/captcha/recaptcha",
                {
                    page_url: TARGET_URL_V3,
                    site_key: RECAPTCHA_KEY_V3,
                    type: "3", // 3 = v3
                    v3_action: "login",
                    v3_min_score: "0.7",
                }
            ];
        case "recaptchav3-enterprise":
            return [
                "/captcha/recaptcha",
                {
                    page_url: TARGET_URL_V3_ENTERPRISE,
                    site_key: RECAPTCHA_KEY_V3_ENTERPRISE,
                    type: "5", // 5 = enterprise v3
                    v3_action: "login",
                    v3_min_score: "0.7",
                }
            ];
        case "cfturnstile":
            return [
                "/captcha/turnstile",
                {
                    page_url: TARGET_URL_CF,
                    site_key: SITE_KEY_CF,
                }
            ];
        case "cfturnstile-invis":
            return [
                "/captcha/turnstile",
                {
                    page_url: TARGET_URL_CF_INVIS,
                    site_key: SITE_KEY_CF_INVIS,
                }
            ];
        case "cfturnstile-non-interactive":
            return [
                "/captcha/turnstile",
                {
                    page_url: TARGET_URL_CF_NON_INTERACTIVE,
                    site_key: SITE_KEY_CF_NON_INTERACTIVE,
                }
            ];
        case "hcaptcha-easy":
            return [
                "/captcha/hcaptcha",
                {
                    page_url: TARGET_URL_HCAP_EASY,
                    site_key: SITE_KEY_HCAP_EASY,
                }
            ];
        case "hcaptcha":
            return [
                "/captcha/hcaptcha",
                {
                    page_url: TARGET_URL_HCAP,
                    site_key: SITE_KEY_HCAP,
                }
            ];
        default:
            throw new Error(`generateBestCaptchaTask: unsupported task type: ${captcha}`);
    }
};

const parseBestCaptchaSolution = (captcha, solution) => {
    switch(captcha){
        case "textcaptcha":
            return solution.text;
        case "recaptchav2":
        case "recaptchav2-invis":
        case "recaptchav3":
        case "recaptchav3-enterprise":
            return solution.gresponse;
        case "cfturnstile":
        case "cfturnstile-invis":
        case "cfturnstile-non-interactive":
        case "hcaptcha-easy":
        case "hcaptcha":
            return solution.solution;
        default:
            throw new Error(`parseBestCaptchaSolution: unsupported task type: ${captcha}`);
    }
};

const reportBestCaptchaAccuracy = async (_captcha, taskId, success) => {
    if(success)
        return;

    const { data } = await api.post(`/captcha/bad/${encodeURIComponent(taskId)}`, {
        access_token: API_KEY_BESTCAPTCHA
    });

    if(data.status !== "updated")
        throw new Error(`Could not report bestcaptchasolver incorrect captcha: ${JSON.stringify(data)}`);
};

const doBestCaptchaSolver = async (db, captcha, filedata) => {
    const [url, data] = await generateBestCaptchaTask(captcha, filedata);
    const createTaskTime = Date.now();
    const { data: taskData, status: taskStatus } = await api.post(url,
        {
            ...data,
            access_token: API_KEY_BESTCAPTCHA
        },
        // image captchas are synchronously returned
        (captcha === "textcaptcha" ? {
            timeout: 120000
        } : undefined)
    );

    if(taskStatus < 200 || taskStatus >= 300 || taskData.status !== "submitted"){
        console.error(`Could not create bestcaptchasolver task (status=${taskStatus})`, JSON.stringify(taskData));
        return null;
    }

    const { id: taskId } = taskData;
    const { lastID: solveId } = await db.run(`INSERT INTO solves (solver, captcha, task_id, text_filename, text_expected) VALUES ('bestcaptchasolver', ?, ?, ?, ?)`, captcha, taskId, filedata?.filename ?? null, filedata?.expected ?? null);

    if(captcha !== "textcaptcha")
        await delay(2000);

    const startTime = Date.now();
    while(Date.now() - startTime < 120000){ // 2 minute timeout
        let axiosResult;
        try{
            axiosResult = await api.get(`/captcha/${encodeURIComponent(taskId)}`, {
                params: {
                    access_token: API_KEY_BESTCAPTCHA
                }
            });
        }catch(err){
            if(axios.isAxiosError(err) && err.code === "ETIMEDOUT")
                continue;

            throw err;
        }

        const { data: resultData, status: resultStatus } = axiosResult;

        if(
            (resultStatus < 200 || resultStatus >= 300) || 
            !["pending", "completed"].includes(resultData.status)
        ){
            console.error(`Bestcaptchasolver task failed (status=${resultStatus})`, JSON.stringify(resultData));
            return [solveId, false, resultStatus, JSON.stringify(resultData), null, null, null, null];
        }

        if(resultData.status === "completed"){
            return [
                solveId,
                true,
                resultStatus,
                JSON.stringify(resultData),
                'from_pipeline',
                createTaskTime,
                Date.now(),
                parseBestCaptchaSolution(captcha, resultData),
                reportBestCaptchaAccuracy,
                taskId
            ];
        }

        await delay(5000);
    }

    //timed out
    return [solveId, false, 0, 'pipeline getTaskResult timeout', null, null, null, null];
};

module.exports = {
    doBestCaptchaSolver
};