from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, filters, ContextTypes
from telegram import Update
import configs
import tracker
import db

TELEGRAM_TOKEN = configs.get_property('TELEGRAM_TOKEN')
DELAY_IN_SECONDS = int(configs.get_property('DELAY_IN_SECONDS'))
DB_PATH = db.DB_PATH

REPO_OWNER, REPO_NAME, BRANCH_NAME = range(3)
already_started_jobs = set()
COMMIT_CHECKER_JOB_NAME = "global_commit_checker"

async def send_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, message_thread_id: int = None) -> None:

    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML', # Directly use string 'HTML'
        message_thread_id=message_thread_id
    )

def build_message(commit, repo_owner, repo_name, branch_name) -> str:
    date = commit.commit.author.date
    message = commit.commit.message
    sha = commit.commit.sha
    modified_files = [file.filename for file in commit.files]
    mess_to_send = f'<b>{repo_name} : <a href="https://github.com/{repo_owner}/{repo_name}/tree/{branch_name}"> {branch_name} </a></b>\n'
    mess_to_send += f'<b><a href="https://github.com/{repo_owner}/{repo_name}/commit/{sha}"> New commit</a></b> found at {date.hour:02}:{date.minute:02} on {date.day}/{date.month}/{date.year}.\n'
    mess_to_send += f'<b>Message</b>: {message}\n'
    
    if modified_files:
        mess_to_send += '<b>Modified files</b>:\n'
        for file in modified_files:
            mess_to_send += f'• {file}\n'
    else:
        mess_to_send += '<b>No modified files</b>.\n'

    return mess_to_send


async def check_commits(context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = db.get_all_entries()
    
    for row in rows:
        chat_id = row['chat_id']
        repo_owner = row['repo_owner']
        repo_name = row['repo_name']
        last_commit_sha = row['last_commit_sha']
        message_thread_id = row.get('message_thread_id')
        branch_name = row.get('branch_name')

        if not all([chat_id, repo_owner, repo_name]):
            logger.warning(f"Skipping entry due to missing data: {row}")
            continue
        try:
            repo = tracker.get_repo(repo_owner, repo_name)
            # Pass branch_name to get_not_reported_commits
            commits = tracker.get_not_reported_commits(repo, last_commit_sha, branch_name)

            for commit_obj in reversed(commits):
                await send_message(context, chat_id, build_message(commit_obj, repo_owner, repo_name, branch_name), message_thread_id)

            if commits: # Check if commits list is not empty
                latest_commit_sha = commits[0].sha
                db.save_commit_state(chat_id, latest_commit_sha)
        except Exception as e:
            print(f"Error checking commits for {repo_owner}/{repo_name} (branch: {branch_name}) for chat {chat_id}: {e}")
            # Optionally send an error message to the user, being careful about spamming
            # send_message(context, chat_id, f"Error checking repository {repo_owner}/{repo_name}. Please check settings or try /start again.", message_thread_id)

async def ensure_commit_checker_job_running(application: Application) -> None:
    """Ensures the global commit checker job is running if there are subscriptions, and stopped if not."""
    job_queue = application.job_queue
    # Important: job_queue might be None if accessed too early or in a non-PTB context.
    # However, post_init and context.application.job_queue should provide it.
    if not job_queue:
        return

    current_checker_jobs = job_queue.get_jobs_by_name(COMMIT_CHECKER_JOB_NAME)
    subscriptions_exist = bool(db.get_all_entries())

    if subscriptions_exist:
        if not current_checker_jobs:
            job_queue.run_repeating(
                callback=check_commits,
                interval=DELAY_IN_SECONDS,
                first=10,  # Start after a small delay
                name=COMMIT_CHECKER_JOB_NAME,
            )
    else:  # No subscriptions
        if current_checker_jobs:
            for job in current_checker_jobs:
                job.schedule_removal()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id # Use effective_chat for groups/channels too
    message_thread_id = getattr(update.message, 'message_thread_id', None) if update.message else None

    context.user_data.clear()
    context.user_data['chat_id'] = chat_id
    context.user_data['message_thread_id'] = message_thread_id

    await send_message(context, chat_id, 'Welcome to the <b>Commit Tracker Bot</b>. Please insert the <b>repository owner</b> (e.g., "octocat").', message_thread_id if update.message and update.message.is_topic_message else None) # Optionally thread welcome
    return REPO_OWNER

async def repo_owner_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    repo_owner_text = update.message.text.strip()
    context.user_data['repo_owner'] = repo_owner_text
    chat_id = context.user_data['chat_id']
    message_thread_id = context.user_data.get('message_thread_id')

    await send_message(context, chat_id, 'Great! Now please insert the <b>repository name</b> (e.g., "Spoon-Knife").', message_thread_id)
    return REPO_NAME


async def repo_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    repo_name_text = update.message.text.strip()
    context.user_data['repo_name'] = repo_name_text
    chat_id = context.user_data['chat_id']
    message_thread_id = context.user_data.get('message_thread_id')

    await send_message(context, chat_id, (
        'Got it. Now, please specify the <b>branch name</b> you want to track '
        '(e.g., "main", "develop").\n\n'
        'If you want to track the <b>default branch</b>, you can send /skip or just type "default".'
    ), message_thread_id)
    return BRANCH_NAME

async def branch_name_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    branch_input = update.message.text.strip()

    chat_id = context.user_data.get('chat_id')
    repo_owner = context.user_data.get('repo_owner')
    repo_name = context.user_data.get('repo_name')
    message_thread_id = context.user_data.get('message_thread_id')

    if not all([chat_id, repo_owner, repo_name]):
        await send_message(context, update.effective_chat.id, "Sorry, something went wrong. Please try /start again.", message_thread_id)
        return ConversationHandler.END

    branch_name_to_track = None
    if branch_input.lower() not in ['/skip', 'default', '']:
        branch_name_to_track = branch_input

    context.user_data['branch_name'] = branch_name_to_track

    try:
        last_commit_sha = tracker.get_last_commit_sha(repo_owner, repo_name, branch_name_to_track)
        if last_commit_sha is None:
            await send_message(context, chat_id, f'Could not find the repository <b>{repo_owner}/{repo_name}</b> or branch "<b>{branch_name_to_track or "default"}</b>". Please check the details and try /start again.', message_thread_id)
            return ConversationHandler.END
    except Exception as e:
        await send_message(context, chat_id, f'Error: Could not access the repository <b>{repo_owner}/{repo_name}</b> (branch: "<b>{branch_name_to_track or "default"}</b>"). Please retry with /start.', message_thread_id)
        return ConversationHandler.END

    db_entry_data = {
        'chat_id': chat_id,
        'repo_owner': repo_owner,
        'repo_name': repo_name,
        'last_commit_sha': last_commit_sha,
        'message_thread_id': message_thread_id,
        'branch_name': branch_name_to_track
    }
    db.init_entry(db_entry_data)

    job_name = str(chat_id)
    # Remove existing job before starting a new one for the same chat_id
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    context.job_queue.run_repeating(
        check_commits,
        interval=DELAY_IN_SECONDS,
        first=10, # Start after 10 seconds
        name=job_name,
        chat_id=chat_id # Pass chat_id to job context if needed by check_commits directly (though it gets it from db)
    )
    if chat_id not in already_started_jobs: # Simple check to add, better job management is ideal
        already_started_jobs.add(chat_id)

    branch_display_name = branch_name_to_track if branch_name_to_track else "default"
    await send_message(context, chat_id, f'You are now subscribed to the repository <b>{repo_owner}/{repo_name}</b> (branch: <b>{branch_display_name}</b>).', message_thread_id)
    await send_message(context, chat_id, 'You will receive a message when a new commit is pushed.', message_thread_id)

    context.user_data.clear()
    return ConversationHandler.END

async def skip_branch_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['branch_name'] = None
    # Need to ensure the update object passed to branch_name_handler is appropriate
    # If branch_name_handler expects a text message, this might need adjustment
    # For simplicity, assuming branch_name_handler can cope or we simulate an empty text
    if update.message:
         update.message.text = "" # Simulate empty text for default branch logic in branch_name_handler
    return await branch_name_handler(update, context)


async def unscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    job_name = str(chat_id)

    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if current_jobs:
        for job in current_jobs:
            job.schedule_removal()

    db.remove_entry(chat_id)
    if chat_id in already_started_jobs:
        already_started_jobs.remove(chat_id)

    await send_message(context, chat_id, 'Successfully unsubscribed.', getattr(update.message, 'message_thread_id', None) if update.message else None)


async def post_init_actions(application: Application) -> None:
    """Actions to run once after the application has been initialized."""

    await ensure_commit_checker_job_running(application)


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(post_init_actions) # Run after Application is ready
        .build()
    )

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            REPO_OWNER: [MessageHandler(filters.TEXT & ~filters.COMMAND, repo_owner_handler)],
            REPO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, repo_name_handler)],
            BRANCH_NAME: [
                CommandHandler('skip', skip_branch_handler),
                MessageHandler(filters.TEXT & ~filters.COMMAND, branch_name_handler)
            ],
        },
        fallbacks=[CommandHandler('unscribe', unscribe)],
        # persistent=True, name="github_tracker_conversation" # For persistence if needed
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('unscribe', unscribe)) # Allow unscribe outside conv

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)


main()
