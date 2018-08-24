/**
 * A Bot for Slack!
 */


/**
 * Define a function for initiating a conversation on installation
 * With custom integrations, we don't have a way to find out who installed us, so we can't message them :(
 */
function onInstallation(bot, installer) {
    if (installer) {
        bot.startPrivateConversation({user: installer}, function (err, convo) {
            if (err) {
                console.log(err);
            } else {
                convo.say('I am a bot that has just joined your team');
                convo.say('You must now /invite me to a channel so that I can be of use!');
            }
        });
    }
}


/**
 * Configure the persistence options
 */
var config = {};
if (process.env.MONGOLAB_URI) {
    var BotkitStorage = require('botkit-storage-mongo');
    config = {
        storage: BotkitStorage({mongoUri: process.env.MONGOLAB_URI}),
    };
} else {
    config = {
        json_file_store: ((process.env.TOKEN)?'./db_slack_bot_ci/':'./db_slack_bot_a/'), //use a different name if an app or CI
    };
}

/**
 * Are being run as an app or a custom integration? The initialization will differ, depending
 */
if (process.env.TOKEN || process.env.SLACK_TOKEN) {
    //Treat this as a custom integration
    var customIntegration = require('./lib/custom_integrations');
    var token = (process.env.TOKEN) ? process.env.TOKEN : process.env.SLACK_TOKEN;
    var controller = customIntegration.configure(token, config, onInstallation);
} else if (process.env.CLIENT_ID && process.env.CLIENT_SECRET && process.env.PORT) {
    //Treat this as an app
    var app = require('./lib/apps');
    var controller = app.configure(process.env.PORT, process.env.CLIENT_ID, process.env.CLIENT_SECRET, config, onInstallation);
} else {
    console.log('Error: If this is a custom integration, please specify TOKEN in the environment. If this is an app, please specify CLIENTID, CLIENTSECRET, and PORT in the environment');
    process.exit(1);
}


/**
 * A demonstration for how to handle websocket events. In this case, just log when we have and have not
 * been disconnected from the websocket. In the future, it would be super awesome to be able to specify
 * a reconnect policy, and do reconnections automatically. In the meantime, we aren't going to attempt reconnects,
 * WHICH IS A B0RKED WAY TO HANDLE BEING DISCONNECTED. So we need to fix this.
 *
 * TODO: fixed b0rked reconnect behavior
 */
// Handle events related to the websocket connection to Slack
controller.on('rtm_open', function (bot) {
    console.log('** The RTM api just connected!');

    /**
     * TODO: Connect to the bot response!
     * Scheduled bot logic goes here!
     */
    var schedule = require('node-schedule');
    var rule = new schedule.RecurrenceRule();
    rule.second = 0;

    var j = schedule.scheduleJob(rule, function(){
        console.log('The answer to life, the universe, and everything!');
    });
});

controller.on('rtm_close', function (bot) {
    console.log('** The RTM api just closed');
    // you may want to attempt to re-open
});


// BEGIN EDITING HERE!

/**
 * Core bot logic goes here!
 */
controller.on('bot_channel_join', function (bot, message) {
    bot.reply(message, "I'm here!")
});

controller.hears(
    ['viirs_check'],
    ['direct_mention', 'mention', 'direct_message'],
    function(bot, message) {        
        var message_list = message.text.split(' ');
        console.log(message_list);
        if (message_list.length == 1) {
            bot.reply(message, 'viirs_check [date_string] [layer_name]');
            bot.reply(message, '-- [date_string] must be be "YYYY-MM-DD" or "today" to check yesterday');
            bot.reply(message, '-- optional: [layer_name] must be empty "VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS_SNPP_CorrectedReflectance_BandsM3-I3-M11", or "VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1"');
            return;
        }

        // Parse the arguments from the message list!
        var datestring = message_list[1];
        function getYesterdayDateString() {
            var d = new Date();
            d.setDate(d.getDate() - 1);

            var month = '' + (d.getMonth() + 1);
            var day = '' + d.getDate();
            var year = d.getFullYear();

            if (month.length < 2) month = '0' + month;
            if (day.length < 2) day = '0' + day;

            return [year, month, day].join('-');
        }
        // Check date_string
        if (datestring.toLowerCase() == "today") {
            datestring = getYesterdayDateString()
        }

        // Parse the layer name!
        var layer_name = ""
        if (message_list.length == 3) {
            var valid_layers = ["VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS_SNPP_CorrectedReflectance_BandsM3-I3-M11", "VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1"]
            var layer_name = message_list[2];

            // Check layer_name
            if (valid_layers.indexOf(layer_name) == -1) {
                bot.reply(message, 'Invalid layer_name');
                bot.reply(message, '-- [layer_name] must be "VIIRS_SNPP_CorrectedReflectance_TrueColor", "VIIRS_SNPP_CorrectedReflectance_BandsM3-I3-M11", or "VIIRS_SNPP_CorrectedReflectance_BandsM11-I2-I1"');
                return;
            }

            bot.reply(message,'Checking *' + layer_name + '* on *' + datestring + '*');
        } else {
            bot.reply(message,'Checking *ALL* VIIRS layers on *' + datestring + '*');
        }

        // Launch a python script
        const { spawn } = require('child_process');
        const pythonProcess = spawn('python', ['validate_viirs.py', datestring, layer_name]);

        // Check for errors
        pythonProcess.on('error', function(err) {
          console.log('Oh no, error: ' + err);
        });

        // Listen for data from python script
        pythonProcess.stdout.on('data', function(data) {
            var data_string = data.toString().trim();
            let string_arr = data_string.split("\n");
            // console.log(data_string);

            // Parse the datastring for values
            var num_lines = string_arr.length;
            var layer_name = "";
            var url_string = "";
            var detection_result_miscolor = "";
            var detection_result_missing_data = "";
            for (var i = 0; i < num_lines; i++) {
                str_parsed = string_arr[i];
                if (str_parsed.startsWith("https:")) {
                    url_string = str_parsed;
                } else if (str_parsed.startsWith("VIIRS_SNPP")) {
                    layer_name = str_parsed;
                } else if (str_parsed.includes("MISCOLOR")) {
                    detection_result_miscolor = str_parsed;
                } else {
                    detection_result_missing_data = str_parsed;
                }
            }
            console.log("Layer: " + layer_name);
            console.log("URL: " + url_string);

            // Issue the parsed commands!
            var image_reply = {
                "attachments": [
                    {
                        "title": layer_name,
                        "image_url": url_string,
                        "text": detection_result_missing_data + "\n" + detection_result_miscolor
                    }
                ]
            };
            bot.reply(message, image_reply);
        });
    }
)

controller.on('slash_command', function (slashCommand, message) {
    switch (message.command) {
        case "/echo": //handle the `/echo` slash command. We might have others assigned to this app too!
            // The rules are simple: If there is no text following the command, treat it as though they had requested "help"
            // Otherwise just echo back to them what they sent us.

            // but first, let's make sure the token matches!
            if (message.token !== process.env.VERIFICATION_TOKEN) return; //just ignore it.

            // if no text was supplied, treat it as a help command
            if (message.text === "" || message.text === "help") {
                slashCommand.replyPrivate(message,
                    "I echo back what you tell me. " +
                    "Try typing `/echo hello` to see.");
                return;
            }

            // If we made it here, just echo what the user typed back at them
            slashCommand.replyPublic(message, "Echo: " + message.text);

            break;
        default:
            slashCommand.replyPublic(message, "I'm afraid I don't know how to " + message.command + " yet.");
    }

})

/**
 * AN example of what could be:
 * Any un-handled direct mention gets a reaction and a pat response!
 */
//controller.on('direct_message,mention,direct_mention', function (bot, message) {
//    bot.api.reactions.add({
//        timestamp: message.ts,
//        channel: message.channel,
//        name: 'robot_face',
//    }, function (err) {
//        if (err) {
//            console.log(err)
//        }
//        bot.reply(message, 'I heard you loud and clear boss.');
//    });
//});
