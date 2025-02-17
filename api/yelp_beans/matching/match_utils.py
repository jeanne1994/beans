import logging
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

import networkx as nx
import pandas as pd
import requests
from database import db
from yelp_beans.logic.config import get_config
from yelp_beans.models import Meeting
from yelp_beans.models import MeetingParticipant
from yelp_beans.models import MeetingSpec
from yelp_beans.models import User


CORP_API_TOKEN = 'xxxx'
CORP_API = 'https://corpapi.yelpcorp.com/v1'

def save_meetings(matches, spec):
    for match in matches:
        # Last element in match may be the key for meeting time
        matched_users = [user for user in match if isinstance(user, User)]
        meeting_key = Meeting(meeting_spec=spec)
        db.session.add(meeting_key)
        for user in matched_users:
            mp = MeetingParticipant(meeting=meeting_key, user=user)
            db.session.add(mp)
        db.session.commit()
        username_list = [user.get_username() for user in matched_users]
        logging.info(meeting_key)
        logging.info(', '.join(username_list))


def get_counts_for_pairs(pairs):
    counts = {}
    for pair in pairs:
        if pair in counts:
            counts[pair] += 1
        else:
            counts[pair] = 1
    return counts


def get_previous_meetings(subscription, cooldown=None):

    if cooldown is None:
        cooldown = get_config()['meeting_cooldown_weeks']

    meetings = defaultdict(list)

    # get all meeting specs from x weeks ago til now
    time_threshold_for_meetings = datetime.now() - timedelta(weeks=cooldown)

    meeting_specs = [
        spec for spec in MeetingSpec.query.filter(
            MeetingSpec.datetime > time_threshold_for_meetings,
            MeetingSpec.meeting_subscription_id == subscription.id
        ).all()
    ]

    logging.info('Previous Meeting History: ')
    logging.info([meeting.datetime.strftime("%Y-%m-%d %H:%M") for meeting in meeting_specs])

    if meeting_specs == []:
        return set([])

    # get all meetings from meeting specs
    meeting_keys = [meeting.id for meeting in Meeting.query.filter(
        Meeting.meeting_spec_id.in_(
            [meet.id for meet in meeting_specs])).all()]

    if meeting_keys == []:
        return set([])

    # get all participants from meetings
    participants = MeetingParticipant.query.filter(
        MeetingParticipant.meeting_id.in_(meeting_keys)
    ).all()

    if participants == []:
        return set([])

    # group by meeting Id
    for participant in participants:
        meetings[participant.meeting.id].append(participant.user)

    # ids are sorted, all matches should be in increasing order by id for the matching algorithm to work
    disallowed_meetings = set([tuple(sorted(meeting, key=lambda Key: Key.id)) for meeting in meetings.values()])

    logging.info('Past Meetings')
    logging.info([tuple([meeting.get_username() for meeting in meeting]) for meeting in disallowed_meetings])

    disallowed_meetings = {tuple([meeting.id for meeting in meeting]) for meeting in disallowed_meetings}

    return disallowed_meetings

def jaccard(list1, list2):
    intersection = len(list(set(list1).intersection(list2)))
    if intersection == 0:
        return 1
    else:
        union = (len(list1) + len(list2)) - intersection
        return float(intersection) / union

def get_pairwise_distance(user_pair, org_graph, employee_df, max_tenure=1000,):
    """
    get the distance between two users.
    The returned distance score is a linear combination of the multiple user attributes' distnace (normalized).
    The importance of each attribute is considered equal.
    User attribute considered:
    1. team/function: distance in the org chart
    2. location - country, city
    3. tenure at Yelp
    4. language

    note: we considered using education and work experience, but think it likely correlates with the first attribute
    """
    user_a, user_b = user_pair
    user_a_attributes = dict(employee_df.loc[user_a])
    user_b_attributes = dict(employee_df.loc[user_b])

    distance = 0

    # org chart distance
    dist_1 = nx.shortest_path_length(org_graph, user_a, user_b)
    dist_1 = dist_1/10  # approx. min-max scaled
    distance += dist_1

    # location
    user_a_city, user_a_country = user_a_attributes["Location"].split(", ")
    user_b_city, user_b_country = user_b_attributes["Location"].split(", ")
    country_dist = 0 if user_a_country == user_b_country else 1
    city_dist = 0 if user_a_city == user_b_city else 1
    dist_2 = country_dist + city_dist
    dist_2 = dist_2/2  # min-max scaled
    distance += dist_2

    # tenure
    dist_3 = abs(int(user_a_attributes["Days_Since_Start"])-int(user_b_attributes["Days_Since_Start"]))
    dist_3 = dist_3/max_tenure
    distance += dist_3

    # language
    lang_similarity = jaccard(user_a_attributes["languages"], user_b_attributes["languages"])
    dist_4 = 1 - lang_similarity
    distance += dist_4

    return distance

def get_meeting_weights(allowed_meetings):
    """
    generate distance score for each user pairs.
    """
    meeting_to_weight = {}

    # fetching employee information and create a pandas dataframe with it
    employees = pd.DataFrame(requests.get(
        f'{CORP_API}/employees',
        headers={'X-API-Key': CORP_API_TOKEN},
    ).json())

    employees = employees.set_index("Employee_ID")
    employees = employees[["Manager_ID", "Cost_Center_-_Name", "Days_Since_Start", "Location", "languages",
                           "Education", "Work_Experience_group", "Pronoun"]]
    max_tenure = max(employees['Days_Since_Start'].astype(int))

    # yelp employee network graph created through reporting line
    G = nx.Graph()
    G.add_edges_from(list(zip(employees.index, employees['Manager_ID'])))

    for user_pair in allowed_meetings:
        users_distance_score = get_pairwise_distance(user_pair, max_tenure, org_graph=G, employee_df=employees)
        meeting_to_weight[user_pair] = users_distance_score

    return meeting_to_weight
