// use sqlite database to save all rows (can export to csv after)
// run 1 concurrent solve PER service. 100 solves per service&captcha pair

const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const fs = require("fs/promises");
const axios = require("axios");
const path = require("path");

const ALLOWED_SOLVERS = ['anticaptcha', '2captcha', 'capsolver', 'capmonster', 'azcaptcha', 'bestcaptchasolver', 'imagetyperz'];
const ALLOWED_CAPTCHAS = ['recaptchav2', 'recaptchav2-invis', 'recaptchav3', 'hcaptcha-easy', 'hcaptcha', 'cfturnstile', 'cfturnstile-invis', 'cfturnstile-non-interactive'];
const ALLOWED_COMBOS = {
    anticaptcha: ["recaptchav2", "recaptchav2-invis", "recaptchav3", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
    "2captcha": ["recaptchav2", "recaptchav2-invis", "recaptchav3", "hcaptcha-easy", "hcaptcha", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
    capsolver: ["recaptchav2", "recaptchav2-invis", "recaptchav3", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
    capmonster: ["recaptchav2", "recaptchav2-invis", "recaptchav3", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
    azcaptcha: ["recaptchav2", "recaptchav2-invis", "recaptchav3"],
    bestcaptchasolver: ["recaptchav2", "recaptchav2-invis", "recaptchav3", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
    imagetyperz: ["recaptchav2", "recaptchav2-invis", "recaptchav3", "hcaptcha-easy", "hcaptcha", "cfturnstile", "cfturnstile-invis", "cfturnstile-non-interactive"],
};
const SOLVES_PER_COMBO = 20;

const {
    RECAPTCHA_SECRET_V2,
    RECAPTCHA_SECRET_V2_INVIS,
    RECAPTCHA_SECRET_V3,
    RECAPTCHA_KEY_V3_ENTERPRISE,
    RECAPTCHA_PROJECT_ID_V3_ENTERPRISE,
    RECAPTCHA_SECRET_V3_ENTERPRISE,
    HCAPTCHA_SECRET_EASY,
    HCAPTCHA_SECRET,
    CF_SECRET,
    CF_SECRET_INVIS,
    CF_SECRET_NON_INTERACTIVE,
    TARGET_URL_V3_ENTERPRISE,
} = require("./constants");

const {
    delay
} = require('./util');

const { doAntiCaptcha } = require('./solvers/anticaptcha');
const { doTwoCaptcha } = require('./solvers/twocaptcha');
const { doCapsolver } = require('./solvers/capsolver');
const { doCapmonster } = require('./solvers/capmonster');
const { doNopecha } = require('./solvers/nopecha');
const { doImageTyperz } = require("./solvers/imagetyperz");
const { doBestCaptchaSolver } = require("./solvers/bestcaptchasolver");
const { doAZCaptcha } = require("./solvers/azcaptcha");

const verifyCaptcha = async (captcha, solution, filedata) => {
    switch(captcha){
        case "textcaptcha":
            const matched = solution === filedata.expected;
            return [
                null,
                matched,
                null,
                null
            ];
        case "recaptchav2":
        case "recaptchav2-invis":
        case "recaptchav3":
        case "hcaptcha-easy":
        case "hcaptcha":
        case "cfturnstile":
        case "cfturnstile-invis":
        case "cfturnstile-non-interactive": {
            let verifyUrl, verifySecret;
            switch(captcha){
                case "recaptchav2":
                    verifyUrl = "https://www.google.com/recaptcha/api/siteverify";
                    verifySecret = RECAPTCHA_SECRET_V2;
                    break;
                case "recaptchav2-invis":
                    verifyUrl = "https://www.google.com/recaptcha/api/siteverify";
                    verifySecret = RECAPTCHA_SECRET_V2_INVIS;
                    break;
                case "recaptchav3":
                    verifyUrl = "https://www.google.com/recaptcha/api/siteverify";
                    verifySecret = RECAPTCHA_SECRET_V3;
                    break;
                case "hcaptcha-easy":
                    verifyUrl = "https://api.hcaptcha.com/siteverify";
                    verifySecret = HCAPTCHA_SECRET_EASY;
                    break;
                case "hcaptcha":
                    verifyUrl = "https://api.hcaptcha.com/siteverify";
                    verifySecret = HCAPTCHA_SECRET;
                    break;
                case "cfturnstile":
                    verifyUrl = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
                    verifySecret = CF_SECRET;
                    break;
                case "cfturnstile-invis":
                    verifyUrl = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
                    verifySecret = CF_SECRET_INVIS;
                    break;
                case "cfturnstile-non-interactive":
                    verifyUrl = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
                    verifySecret = CF_SECRET_NON_INTERACTIVE;
            }

            verifyResponse = await axios.post(verifyUrl, new URLSearchParams({
                secret: verifySecret,
                response: solution
            }).toString(), {
                validateStatus: null
            });

            const { data } = verifyResponse;
            return [verifyResponse, data.success ?? null, data.score ?? null, data["error-codes"]?.join(", ") ?? ""];
        }
        case "recaptchav3-enterprise": {
            verifyResponse = await axios.post(
                `https://recaptchaenterprise.googleapis.com/v1/projects/${encodeURIComponent(RECAPTCHA_PROJECT_ID_V3_ENTERPRISE)}/assessments?key=${encodeURIComponent(RECAPTCHA_SECRET_V3_ENTERPRISE)}`,
                {
                    event: {
                        token: solution,
                        siteKey: RECAPTCHA_KEY_V3_ENTERPRISE,
                        expectedAction: 'login',
                        requestedUri: TARGET_URL_V3_ENTERPRISE
                    }
                }, {
                    validateStatus: null
                }
            );

            const { data } = verifyResponse;
            const invalidReason = data.tokenProperties?.invalidReason;
            const riskReasons = data.riskAnalysis?.reasons;
            const errorMessage = `${invalidReason ? `invalidReason: ${invalidReason} ${riskReasons?.length ? `, ` : ""}` : ""}${riskReasons?.length ? `riskReasons: [${data.riskAnalysis?.reasons?.join(", ")}]` : ""}`;
            
            return [
                verifyResponse,
                data.tokenProperties?.valid ?? null,
                data.riskAnalysis?.score ?? null,
                errorMessage,
            ];
        }
        default:
            throw new Error(`Verification not implemented yet for captcha type: ${captcha}`);
    }
};

const solveCaptcha = async (db, solver, captcha, filedata) => {
    if(!ALLOWED_SOLVERS.includes(solver) || !ALLOWED_CAPTCHAS.includes(captcha))
        throw new Error(`invalid solver/captcha (solver=${solver}, captcha=${captcha})`);

    // solve captcha
    let result;
    switch(solver){
        case "anticaptcha":
            result = await doAntiCaptcha(db, captcha, filedata);
            break;
        case "2captcha":
            result = await doTwoCaptcha(db, captcha, filedata);
            break;
        case "capsolver":
            result = await doCapsolver(db, captcha, filedata);
            break;
        case "capmonster":
            result = await doCapmonster(db, captcha, filedata);
            break;
        case "nopecha":
            result = await doNopecha(db, captcha, filedata);
            break;
        case "imagetyperz":
            result = await doImageTyperz(db, captcha, filedata);
            break;
        case "bestcaptchasolver":
            result = await doBestCaptchaSolver(db, captcha, filedata);
            break;
        case "azcaptcha":
            result = await doAZCaptcha(db, captcha, filedata);
            break;
        default:
            throw new Error(`Solving not implemented yet for captcha type: ${captcha}`);
    }

    if(result){
        const [
            solveId,
            solverSuccess,
            solverStatusCode,
            solverResult,
            timePrecision,
            startTime,
            finishTime,
            solution,
            reportVerification,
            taskId
        ] = result;

        await db.run(
            `
            UPDATE solves SET
                solver_success=?,
                solver_status_code=?,
                solver_result=?,
                time_precision=?,
                startTime=?,
                finishTime=?
            WHERE id = ?
            `,
            solverSuccess,
            solverStatusCode,
            solverResult,
            timePrecision,
            startTime,
            finishTime,
            solveId
        );

        if(solverSuccess){
            const [ verifyResponse, verifySuccess, verifyScore, verifyErrorMessage ] = await verifyCaptcha(captcha, solution, filedata);

            if(reportVerification){
                let metCriteria = verifySuccess;
                if(metCriteria && (captcha === "recaptchav3" || captcha === "recaptchav3-enterprise")){
                    metCriteria = verifyScore > 0.5; // we want minimum score of 0.5 for the site
                }

                // Only report if verification secrets are set
                const verifySecret = captcha === "recaptchav2" ? RECAPTCHA_SECRET_V2 :
                                   captcha === "recaptchav2-invis" ? RECAPTCHA_SECRET_V2_INVIS :
                                   captcha === "recaptchav3" ? RECAPTCHA_SECRET_V3 :
                                   captcha === "hcaptcha-easy" ? HCAPTCHA_SECRET_EASY :
                                   captcha === "hcaptcha" ? HCAPTCHA_SECRET :
                                   captcha === "cfturnstile" ? CF_SECRET :
                                   captcha === "cfturnstile-invis" ? CF_SECRET_INVIS :
                                   captcha === "cfturnstile-non-interactive" ? CF_SECRET_NON_INTERACTIVE : null;
                
                if (verifySecret) {
                    reportVerification(captcha, taskId, metCriteria, verifyErrorMessage)
                        .catch((err) => {
                            console.error(`Error reporting correct/incorrect status (solver=${solver}, captcha=${captcha})`, err);
                        });
                }
            }

            await db.run(
                `
                UPDATE solves SET
                    verify_success=?,
                    verify_status_code=?,
                    verify_result=?,
                    verify_score=?,
                    text_received=?
                WHERE id=?`,
                verifySuccess,
                verifyResponse?.status ?? null,
                verifyResponse?.data != null ? JSON.stringify(verifyResponse.data) : null,
                verifyScore,
                captcha === "textcaptcha" ? solution : null,
                solveId
            );
        }
    }

    // delay 0.5s-1s
    await delay(Math.random() * 500 + 500);
    return !!result;
};

const solveThread = (db, solver, mappingEntries) => {
    return (async () => {
        const nextTask = mappingEntries
            .filter(([captcha, solves]) => solves < SOLVES_PER_COMBO)[0];

        //finished!
        if(!nextTask)
            return;

        const captcha = nextTask[0];
        const taskAdded = await solveCaptcha(db, solver, captcha);
        if(taskAdded){
            nextTask[1]++; // increment amount of solves
        }

        return solveThread(db, solver, mappingEntries);
    })()
        .catch(err => console.error(`An error occurred while solving (solver=${solver})`, err));
};

const main = async () => {
    const db = await open({
        filename: './database.db',
        driver: sqlite3.Database,
    });

    // create database
    await db.exec(`
        CREATE TABLE IF NOT EXISTS \`solves\` (
            id INTEGER NOT NULL PRIMARY KEY,
            solver text CHECK(solver IN ('anticaptcha', '2captcha', 'capsolver', 'capmonster', 'nopecha', 'deathbycaptcha', 'imagetyperz', 'bestcaptchasolver', 'azcaptcha')) NOT NULL,
            captcha text CHECK(captcha IN ('recaptchav2', 'recaptchav2-invis', 'recaptchav3', 'recaptchav3-enterprise', 'hcaptcha-easy', 'hcaptcha', 'cfturnstile', 'cfturnstile-invis', 'cfturnstile-non-interactive', 'funcaptcha', 'awscaptcha', 'textcaptcha')) NOT NULL,
            task_id text NOT NULL,
            solver_success boolean,
            solver_status_code numeric(3),
            solver_result text,
            verify_success boolean,
            verify_status_code numeric(3),
            verify_result text,
            verify_score numeric(1,2),
            time_precision text CHECK(time_precision IN ('from_solver','from_pipeline')),
            startTime timestamp(4),
            finishTime timestamp(4),
            text_filename text,
            text_expected text,
            text_received text
        );
    `);

    const countsMapping = {};
    for(const [solver, captchas] of Object.entries(ALLOWED_COMBOS)){
        const mapping = {};
        countsMapping[solver] = mapping;
        for(const captcha of captchas){
            if(captcha === 'textcaptcha')
                continue;
            mapping[captcha] = 0;
        }
    }

    const counts = await db.all(`SELECT solver, captcha, COUNT(*) as count FROM solves GROUP BY solver, captcha`);
    for(const { solver, captcha, count } of counts){
        if(countsMapping[solver] && countsMapping[solver][captcha] === 0) // skip anything not in ALLOWED_COMBOS
            countsMapping[solver][captcha] = count;
    }

    // Text captcha handling removed

    const threads = [];
    for(const [solver, mapping] of Object.entries(countsMapping)){
        threads.push(solveThread(db, solver, Object.entries(mapping)));
    }

    await Promise.all(threads);
    console.log("done!");
};
main();