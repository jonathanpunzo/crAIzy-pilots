import csv
import json
import math


CONTROLLER_DATASET_FILENAME = 'torcs_ps4_dataset_mattia15.csv'

CONTROLLER_DATASET_COLUMNS = [
    'steer', 'accel', 'brake', 'gear',
    'speedX', 'speedY', 'speedZ',
    'wheelSpinVel', 'z', 'track', 'trackPos', 'angle',
    'rpm', 'damage', 'distFromStart',
]

TRAINING_COLUMNS = [
    'speedX', 'speedY', 'speedZ', 'trackPos', 'angle', 'rpm', 'damage', 'distFromStart',
    'front', 'front_window', 'left_front', 'right_front', 'curve_signal',
    'is_straight', 'is_corner', 'is_sharp_corner', 'clean_sample',
    'target_steer', 'target_accel', 'target_brake', 'target_gear',
]

STRAIGHT_FRONT_DISTANCE = 135
CORNER_FRONT_DISTANCE = 90
SHARP_FRONT_DISTANCE = 45
CORNER_DIFF_THRESHOLD = 28
SHARP_DIFF_THRESHOLD = 70


def clip(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        value = float(value)
        if math.isnan(value) or math.isinf(value):
            return default
        return value
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def average(values):
    return sum(values) / len(values) if values else 0.0


def parse_vector(value, length, default_value):
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            try:
                value = json.loads(cleaned)
            except Exception:
                cleaned = cleaned.replace('[', ' ').replace(']', ' ').replace(',', ' ')
                value = cleaned.split()
        else:
            value = []

    if not isinstance(value, (list, tuple)):
        value = [default_value] * length

    values = [safe_float(item, default_value) for item in value]

    if len(values) < length:
        values += [default_value] * (length - len(values))
    elif len(values) > length:
        values = values[:length]

    return values


def validate_controller_header(header):
    return list(header) == CONTROLLER_DATASET_COLUMNS


def read_controller_dataset(path=CONTROLLER_DATASET_FILENAME):
    with open(path, newline='', encoding='utf-8') as dataset_file:
        reader = csv.DictReader(dataset_file)
        if not validate_controller_header(reader.fieldnames or []):
            raise ValueError('Dataset PS4 non compatibile: colonne diverse dal controller.')

        for row in reader:
            yield row


def row_to_sensors(row):
    return {
        'speedX': safe_float(row.get('speedX')),
        'speedY': safe_float(row.get('speedY')),
        'speedZ': safe_float(row.get('speedZ')),
        'wheelSpinVel': parse_vector(row.get('wheelSpinVel'), 4, 0.0),
        'z': safe_float(row.get('z')),
        'track': parse_vector(row.get('track'), 19, 200.0),
        'trackPos': safe_float(row.get('trackPos')),
        'angle': safe_float(row.get('angle')),
        'rpm': safe_float(row.get('rpm')),
        'damage': safe_float(row.get('damage')),
        'distFromStart': safe_float(row.get('distFromStart')),
    }


def row_to_action(row):
    return {
        'steer': clip(safe_float(row.get('steer')), -1.0, 1.0),
        'accel': clip(safe_float(row.get('accel')), 0.0, 1.0),
        'brake': clip(safe_float(row.get('brake')), 0.0, 1.0),
        'gear': safe_int(row.get('gear'), 1),
    }


def analyze_track_from_sensors(S):
    track = [max(0.0, value) for value in parse_vector(S.get('track'), 19, 200.0)]
    front = track[9]
    left_front = average(track[6:9])
    right_front = average(track[10:13])
    front_window = average(track[7:12])
    curve_signal = right_front - left_front

    is_straight = front > STRAIGHT_FRONT_DISTANCE and abs(curve_signal) < CORNER_DIFF_THRESHOLD
    is_sharp_corner = front < SHARP_FRONT_DISTANCE or abs(curve_signal) > SHARP_DIFF_THRESHOLD
    is_corner = not is_straight or front < CORNER_FRONT_DISTANCE or abs(curve_signal) > CORNER_DIFF_THRESHOLD

    return {
        'front': front,
        'front_window': front_window,
        'left_front': left_front,
        'right_front': right_front,
        'curve_signal': curve_signal,
        'is_straight': is_straight,
        'is_corner': is_corner,
        'is_sharp_corner': is_sharp_corner,
    }


def is_clean_sample(S):
    track = parse_vector(S.get('track'), 19, 200.0)
    return abs(S.get('trackPos', 0.0)) <= 1.0 and min(track) >= 0.0 and S.get('speedX', 0.0) >= -1.0


def build_training_sample(row):
    S = row_to_sensors(row)
    A = row_to_action(row)
    track_info = analyze_track_from_sensors(S)

    sample = {
        'speedX': S['speedX'],
        'speedY': S['speedY'],
        'speedZ': S['speedZ'],
        'trackPos': S['trackPos'],
        'angle': S['angle'],
        'rpm': S['rpm'],
        'damage': S['damage'],
        'distFromStart': S['distFromStart'],
        'front': track_info['front'],
        'front_window': track_info['front_window'],
        'left_front': track_info['left_front'],
        'right_front': track_info['right_front'],
        'curve_signal': track_info['curve_signal'],
        'is_straight': int(track_info['is_straight']),
        'is_corner': int(track_info['is_corner']),
        'is_sharp_corner': int(track_info['is_sharp_corner']),
        'clean_sample': int(is_clean_sample(S)),
        'target_steer': A['steer'],
        'target_accel': A['accel'],
        'target_brake': A['brake'],
        'target_gear': A['gear'],
    }

    for index, value in enumerate(S['track']):
        sample['track_%02d' % index] = value

    for index, value in enumerate(S['wheelSpinVel']):
        sample['wheelSpinVel_%d' % index] = value

    return sample


def load_training_samples(path=CONTROLLER_DATASET_FILENAME, clean_only=True):
    samples = []
    for row in read_controller_dataset(path):
        sample = build_training_sample(row)
        if not clean_only or sample['clean_sample']:
            samples.append(sample)
    return samples


def modular_action_for_row(row, previous_action=None):
    import torcs_jm_par_modulare as modular

    S = row_to_sensors(row)
    action, track_info = modular.calculate_action_from_sensors(S, previous_action)
    return action, track_info


def compare_with_modular(row, previous_action=None):
    manual_action = row_to_action(row)
    modular_action, track_info = modular_action_for_row(row, previous_action)

    return {
        'manual_steer': manual_action['steer'],
        'manual_accel': manual_action['accel'],
        'manual_brake': manual_action['brake'],
        'manual_gear': manual_action['gear'],
        'modular_steer': modular_action['steer'],
        'modular_accel': modular_action['accel'],
        'modular_brake': modular_action['brake'],
        'modular_gear': modular_action['gear'],
        'steer_error': manual_action['steer'] - modular_action['steer'],
        'accel_error': manual_action['accel'] - modular_action['accel'],
        'brake_error': manual_action['brake'] - modular_action['brake'],
        'gear_error': manual_action['gear'] - modular_action['gear'],
        'front': track_info['front'],
        'curve_signal': track_info['curve_signal'],
        'is_straight': int(track_info['is_straight']),
        'is_corner': int(track_info['is_corner']),
        'is_sharp_corner': int(track_info['is_sharp_corner']),
    }


def summarize_dataset(path=CONTROLLER_DATASET_FILENAME):
    summary = {
        'rows': 0,
        'clean_rows': 0,
        'straight_rows': 0,
        'corner_rows': 0,
        'sharp_corner_rows': 0,
        'avg_speed': 0.0,
        'max_speed': 0.0,
        'avg_abs_steer': 0.0,
        'max_abs_trackPos': 0.0,
        'max_abs_speedY': 0.0,
    }

    speed_sum = 0.0
    abs_steer_sum = 0.0

    for row in read_controller_dataset(path):
        S = row_to_sensors(row)
        A = row_to_action(row)
        track_info = analyze_track_from_sensors(S)

        summary['rows'] += 1
        summary['clean_rows'] += int(is_clean_sample(S))
        summary['straight_rows'] += int(track_info['is_straight'])
        summary['corner_rows'] += int(track_info['is_corner'])
        summary['sharp_corner_rows'] += int(track_info['is_sharp_corner'])
        summary['max_speed'] = max(summary['max_speed'], S['speedX'])
        summary['max_abs_trackPos'] = max(summary['max_abs_trackPos'], abs(S['trackPos']))
        summary['max_abs_speedY'] = max(summary['max_abs_speedY'], abs(S['speedY']))
        speed_sum += S['speedX']
        abs_steer_sum += abs(A['steer'])

    if summary['rows']:
        summary['avg_speed'] = speed_sum / summary['rows']
        summary['avg_abs_steer'] = abs_steer_sum / summary['rows']

    return summary
