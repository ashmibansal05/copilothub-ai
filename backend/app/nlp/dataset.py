"""Training data for the intent classifier.

IMPORTANT, read before trusting any number computed from this file:
  * It is SYNTHETIC: every sentence was written by hand by the project author.
  * It is SMALL: 18 training examples per class (234 in total).
  * TEST_EXAMPLES were written separately and are NEVER used for training, but they come from
    the same author, so scores on them are optimistic compared with real users.
Real data collection: every classified instruction is logged in the `intent_samples` table
together with what the human finally did; `python -m app.nlp.train --include-feedback`
retrains on those confirmed samples.
"""

TRAIN: dict[str, list[str]] = {
    "APPROVE": [
        "Approve", "Looks good, approved.", "Yes, go ahead and finalize it.",
        "That's fine, publish the report.", "I approve this draft.", "Great work, approved.",
        "LGTM", "Approved, you can finish now.", "Yes, that is correct, proceed.",
        "The summary is accurate, approve it.", "Go ahead with the final report.",
        "Sounds good to me, approved.", "Perfect, ship it.", "I'm happy with this result, approve.",
        "Yes, finish the report.", "Accept this draft.", "This looks right, please finalize.",
        "OK, approved.",
    ],
    "REJECT": [
        "Reject this draft.", "No, this is not acceptable.", "I do not approve this report.",
        "This draft is wrong, redo it.", "Not good enough, try again.", "Rejected.",
        "No, the summary misses the main points.", "I disagree with this conclusion, please revise it.",
        "This is not what I wanted, reject.", "The report is incomplete, do not approve.",
        "Decline this version.", "That's inaccurate, send it back.", "Redo the draft, it is too shallow.",
        "I can't accept this result.", "Needs more work, rejected.", "No, don't finalize it yet.",
        "This doesn't answer my question, rewrite it.", "Thumbs down on this draft.",
    ],
    "CORRECT": [
        "That's wrong, AWS offers a free tier for twelve months, not six.",
        "Correction: the price is in euros, not dollars.",
        "You made a mistake, Azure does support hybrid licensing.",
        "Actually the startup has five employees, not ten.",
        "That figure is incorrect, it should be 200 dollars per month.",
        "No, Google Cloud's free credit is 300 dollars.",
        "You got the date wrong, it launched in 2015.",
        "Fix this: the comparison should include support costs.",
        "The cost estimate is off, please correct it.",
        "Wrong region, we are based in Europe.",
        "That claim is false, please correct it.",
        "You misread the pricing table, the compute price is lower.",
        "Correction: our budget is monthly, not yearly.",
        "I think you mixed up Azure and AWS in step three.",
        "The numbers in the second step are incorrect.",
        "Please correct that, the team uses Python not Java.",
        "That is not accurate, the free tier excludes storage.",
        "You have an error in the calculation.",
    ],
    "PAUSE": [
        "Pause", "Pause the research for now.", "Please stop for a moment.", "Hold on, wait a second.",
        "Pause the agent.", "Stop working for now.", "Wait, don't continue yet.", "Can you pause here?",
        "Freeze for a bit, I need to check something.", "Halt the research temporarily.",
        "Let's take a break.", "Please hold off on the next step.", "Pause execution.",
        "Give us a minute before continuing.", "Hang on a moment.", "Stop for now, we need to discuss.",
        "Temporarily stop the agent.", "Pause please.",
    ],
    "RESUME": [
        "Resume", "Continue the research.", "You can continue now.", "Go on.", "Resume the agent.",
        "Please carry on.", "OK, keep going.", "Continue where you stopped.",
        "Start again from where you paused.", "Proceed with the next step.",
        "We are ready, resume please.", "Unpause the agent.", "Carry on with the plan.",
        "You can proceed now.", "Back to work, continue.", "Continue please.",
        "Restart the research from the pause.", "Keep going with the remaining steps.",
    ],
    "MODIFY_TASK": [
        "Change the task to compare only pricing.", "Let's change the goal: focus on security instead.",
        "Modify the task so it covers Oracle Cloud as well.",
        "Update the task: the report should be for a medium company.",
        "New task: compare managed databases on the three clouds.",
        "Switch the research topic to container services.",
        "Instead of a full report, only write a short comparison.",
        "Change the scope to startups in India.",
        "Please redefine the objective: evaluate vendor lock-in.",
        "The task is now to compare machine learning platforms.",
        "Narrow the task to serverless offerings only.", "Expand the task to include on-premise options.",
        "Alter the assignment to focus on cost optimization.",
        "Revise the task description to mention compliance requirements.",
        "I want to change what you are researching: look into Kubernetes hosting.",
        "Replace the task with a comparison of CDN providers.",
        "Change the research objective to disaster recovery.", "Make the task about data egress fees.",
    ],
    "ADD_CONSTRAINT": [
        "Use official cloud provider documentation.", "Prefer official documentation as sources.",
        "Keep the report under 500 words.", "Only use sources published in the last two years.",
        "Always cite your sources.", "You must write in a formal tone.",
        "Focus on pricing for small teams.", "Only consider providers with a free tier.",
        "Never include marketing material.", "Limit the comparison to three providers.",
        "Make sure every claim has a source.", "Wikipedia is allowed as a source.",
        "Please prefer academic papers over blogs.", "Use primary sources whenever possible.",
        "Add a rule: no speculation.", "The report must include a cost table.",
        "Rely mainly on vendor documentation.", "Add a constraint that sources must be in English.",
    ],
    "REMOVE_CONSTRAINT": [
        "Remove the constraint about Wikipedia.", "You can use Wikipedia again.",
        "Drop the rule about official documentation.", "Delete the word limit constraint.",
        "Cancel the restriction on blogs.", "Forget the rule about citations.",
        "Lift the ban on Reddit.", "That constraint is no longer needed, remove it.",
        "Undo the Wikipedia exclusion.", "Stop enforcing the formal tone rule.",
        "Get rid of the source restriction.", "Take away the free tier requirement.",
        "Revoke the preference for official docs.", "Remove the last constraint.",
        "Wikipedia is fine again, remove the restriction.", "Disable the rule that limits providers.",
        "Please remove the no speculation rule.", "Clear the constraint on publication dates.",
    ],
    "ADD_INFORMATION": [
        "The startup has two developers and no ops engineer.", "FYI our monthly cloud budget is 500 dollars.",
        "Note that we already use Microsoft 365.", "For context, the product is a mobile app backend.",
        "We expect around 10000 users in the first year.",
        "Our team is based in Germany, so data residency matters.",
        "The company runs mostly Python services.", "By the way, we need GDPR compliance.",
        "Here is some background: we are pre-revenue.", "Additional info: the CTO prefers managed services.",
        "Our traffic is spiky, mostly on weekends.", "We have free credits from an accelerator program.",
        "Keep in mind we have no dedicated security team.",
        "The database is PostgreSQL with about 50 GB of data.",
        "Information for you: launch is planned for March.", "We use GitHub Actions for deployment.",
        "Please note that latency to Asia is important.", "The founders have experience with Kubernetes.",
    ],
    "REJECT_SOURCE": [
        "Don't use Wikipedia.", "Stop using Wikipedia.", "Do not cite Reddit.",
        "Exclude blogs from the sources.", "Ignore the Medium article, it is unreliable.",
        "Never use Quora as a source.", "Remove Wikipedia from the sources.",
        "That website is not trustworthy, do not use it.", "Please avoid vendor marketing pages.",
        "Reject the first source, it is biased.", "Drop the blog posts as sources.", "No Wikipedia please.",
        "Do not rely on Stack Overflow answers.", "Skip the Forbes article.",
        "I don't trust that source, discard it.", "Stop citing social media.",
        "Disregard anything from Wikipedia.", "Wikipedia is not a valid source for this report.",
    ],
    "CHANGE_SOURCE": [
        "Replace Wikipedia with official documentation.", "Use official documentation instead of blogs.",
        "Swap the blog posts for vendor documentation.", "Instead of Wikipedia, use the cloud provider docs.",
        "Switch from Reddit to peer reviewed articles.", "Use AWS documentation rather than Medium articles.",
        "Rather than marketing pages, rely on technical whitepapers.",
        "Change the source from the blog to the official pricing page.",
        "Substitute Quora with Stack Overflow.",
        "Take sources from Gartner reports instead of random blogs.",
        "Use academic papers in place of news articles.", "Replace the Forbes article with a primary source.",
        "Prefer the Azure docs over third party tutorials.",
        "Swap Wikipedia for encyclopedic entries from Britannica.",
        "Use GitHub documentation in place of forum threads.",
        "Instead of Medium, cite the engineering blogs of the vendors.",
        "Move from secondary sources to official sources.",
        "Replace the analyst blog with the vendor's own documentation.",
    ],
    "QUESTION": [
        "Why did you choose AWS first?", "What is the free tier limit for Azure?",
        "How confident are you in this result?", "Which sources have you used so far?",
        "Can you explain this step?", "What does the next step involve?", "Why was Wikipedia filtered?",
        "How long will this take?", "Did you check Google Cloud pricing?", "What is your current plan?",
        "Is this comparison based on real data?", "Where did that number come from?",
        "Do you have documentation about support plans?", "How many sources are there so far?",
        "What happens after the comparison?", "Are there any risks you have found?",
        "Which provider looks cheapest right now?", "Could you tell me what you found in step two?",
    ],
    "COMMENT": [
        "Nice work so far.", "Interesting, thanks for the update.", "I'll review this later.",
        "Good progress everyone.", "Thanks!", "This is taking a while but fine.",
        "I am reading the sources now.", "Cool, keep me posted.", "Let's discuss this in our meeting tomorrow.",
        "Not sure yet what I think about this.", "Haha, that's a surprising result.",
        "I'm back, catching up on the timeline.", "Noted.", "Looks promising.", "That was fast.",
        "Thanks, this is helpful for our planning.", "I'll check with my co-founder.",
        "Interesting choice of sources.",
    ],
}

# Held out: never used for training. Phrased differently from TRAIN on purpose.
TEST: dict[str, list[str]] = {
    "APPROVE": ["Yes that works, finalize it.", "Everything is correct, approved.", "Okay publish the report as is."],
    "REJECT": ["I'm not satisfied, please redo the whole thing.", "No good, discard this draft.", "Reject it, it ignores our budget."],
    "CORRECT": ["Actually it's 20 developers, not two.", "Wrong: Azure's free credit is not 100 dollars.", "That price should be monthly rather than annual."],
    "PAUSE": ["Wait a moment please.", "Stop for now.", "Put the research on hold."],
    "RESUME": ["Okay, you may carry on.", "Let's continue.", "Resume working please."],
    "MODIFY_TASK": ["Change what we're researching to storage costs.", "Update the assignment to cover Alibaba Cloud.", "Let's make the task about network performance instead."],
    "ADD_CONSTRAINT": ["Always prefer official docs.", "Keep every answer short.", "Only use English sources."],
    "REMOVE_CONSTRAINT": ["Take off the rule about blogs.", "Forget the Wikipedia restriction.", "Remove the word limit."],
    "ADD_INFORMATION": ["We're a team of three in Poland.", "For your information, we use Terraform.", "Our budget is capped at 300 euros."],
    "REJECT_SOURCE": ["Don't trust Medium posts.", "Skip Wikipedia entirely.", "I don't want Reddit in the sources."],
    "CHANGE_SOURCE": ["Use vendor docs rather than blogs.", "Replace Reddit with official forums.", "Instead of Wikipedia take Britannica."],
    "QUESTION": ["What did you find about Azure pricing?", "How reliable is this source?", "Why is the progress at fifty percent?"],
    "COMMENT": ["Thanks for the update.", "I'll look at it after lunch.", "Impressive speed."],
}

INTENTS: list[str] = list(TRAIN)


def flatten(data: dict[str, list[str]]) -> list[tuple[str, str]]:
    return [(text, label) for label, texts in data.items() for text in texts]


TRAIN_EXAMPLES = flatten(TRAIN)
TEST_EXAMPLES = flatten(TEST)