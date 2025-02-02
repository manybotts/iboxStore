Deployment
Deploy on Heroku:

heroku config:set BOT_TOKEN=<your_bot_token>
heroku config:set MONGO_URI=<your_mongodb_connection_string>
heroku config:set ADMINS=<admin_chat_id_1>,<admin_chat_id_2>
heroku config:set HEROKU_URL=https://<your_heroku_app_name>.herokuapp.com

Deploy on Koyeb

koyeb deploy --env BOT_TOKEN=<your_bot_token> \
             --env MONGO_URI=<your_mongodb_connection_string> \
             --env ADMINS=<admin_chat_id_1>,<admin_chat_id_2> \
             --env HEROKU_URL=https://<your_koyeb_app_name>.koyeb.app


# iboxStore
