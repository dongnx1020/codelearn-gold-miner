import sys
import socket
import json

HOST = "localhost"
PORT = 1234
if len(sys.argv) == 3:
    HOST = str(sys.argv[1])
    PORT = int(sys.argv[2])

class Map:
    LAND = 0
    FOREST = 1
    TRAP = 2
    SWAMP = 3
    
    def __init__(self, width, height, golds, obstacles):
        self.max_x = width - 1
        self.max_y = height - 1
        self.width = width
        self.height = height
        self.golds = None
        self.obstacles = None
        self.__parse_map(golds, obstacles)

    def __parse_map(self, golds, obstacles):
        self.golds = [[0 for i in range(self.width)] for j in range(self.height)]
        self.obstacles = [[1 for i in range(self.width)] for j in range(self.height)]
        for cell in golds:
            x = cell['posx']
            y = cell['posy']
            self.golds[y][x] = cell['amount']
            self.obstacles[y][x] = 4
        for cell in obstacles:
            x = cell['posx']
            y = cell['posy']
            if cell['type'] == self.LAND:
                self.obstacles[y][x] = 1
            if cell['type'] == self.TRAP:
                self.obstacles[y][x] = 2
            if cell['type'] == self.FOREST:
                self.obstacles[y][x] = 3
            if cell['type'] == self.SWAMP:
                self.obstacles[y][x] = 3

    def update(self, golds):
        for y in range(self.height):
            for x in range(self.width):
                if self.obstacles[y][x] == 4:
                    self.golds[y][x] = 0
                    self.obstacles[y][x] = 1
        for cell in golds:
            x = cell['posx']
            y = cell['posy']
            self.golds[y][x] = cell['amount']
            self.obstacles[y][x] = 4

    def gold_amount(self, x, y):
        if x in range(self.width) and y in range(self.height):
            return self.golds[y][x]
        else:
            return 0
    
    def gold_amount_square(self, x, y, window):
        total = 0
        for i in range(window['height']):
            for j in range(window['width']):
                total += self.gold_amount(x+j, y+i)
        return total

    def gold_total(self):
        total = 0
        for y in range(self.height):
            for x in range(self.width):
                total += self.golds[y][x]
        return total

    def cell_energy(self, x, y):
        if x in range(self.width) and y in range(self.height):
            return self.obstacles[y][x]
        else:
            return -1

    def cell_around(self, x, y):
        cell_up = self.cell_energy(x, y-1)
        cell_down = self.cell_energy(x, y+1)
        cell_left = self.cell_energy(x-1, y)
        cell_right = self.cell_energy(x+1, y)
        return cell_up, cell_down, cell_left, cell_right


class Miner:
    ACTION_GO_LEFT = 0
    ACTION_GO_RIGHT = 1
    ACTION_GO_UP = 2
    ACTION_GO_DOWN = 3
    ACTION_FREE = 4
    ACTION_CRAFT = 5

    def __init__(self, game_info):
        self.id = None
        self.x = 0
        self.y = 0
        self.energy = 9999
        self.score = 0
        self.lastAction = None
        self.map = None
        self.intelligent = None
        self.choose = None
        self.__parse_game_info(game_info)

    def __str__(self):
        return "Player: {}\n" \
               "Position: ({}, {})\n" \
               "Energy: {}\n" \
               "lastAction: {}\n".format(self.id, self.x, self.y, self.energy, self.lastAction)

    def __parse_game_info(self, game_info):
        self.id = game_info["playerId"]
        self.x = game_info["posx"]
        self.y = game_info["posy"]
        self.energy = game_info["energy"]
        self.map = Map(game_info["gameinfo"]["width"], game_info["gameinfo"]["height"], game_info["gameinfo"]["golds"], game_info["gameinfo"]["obstacles"])
        self.intelligent = {
            'rest_counter': 0,
            'step_counter': game_info['gameinfo']['steps'],
            'players': None,
            'same_position': game_info['gameinfo']['numberOfPlayers'],
            'epsilon': None,
            'target': None,
            'corner': None,
            'window': None
        }

    def count_player(self, x, y):
        count = 0
        for player in self.intelligent["players"]:
            if (player["posx"], player["posy"]) == (x, y):
                count += 1
        return count

    def update_state(self, game_state):
        for player in game_state["players"]:
            if player["playerId"] == self.id:
                self.x = player["posx"]
                self.y = player["posy"]
                self.energy = player["energy"]
                self.score = player["score"]
                self.lastAction = player["lastAction"]
        self.map.update(game_state["golds"])
        self.intelligent['step_counter'] -= 1
        self.intelligent['players'] = game_state['players']
        self.intelligent['same_position'] = self.count_player(self.x, self.y)

    def tactic_window(self):
        gold_total = self.map.gold_total()
        steps = self.intelligent['step_counter']
        if steps < 30 or gold_total < 1500:
            self.intelligent['window'] = {'width': 21, 'height': 9}
        elif steps < 70 or gold_total < 3000:
            self.intelligent['window'] = {'width': 4, 'height': 4}
        else:
            self.intelligent['window'] = {'width': 6, 'height': 6}

    def tactic_choose(self):
        gold_total = self.map.gold_total()
        steps = self.intelligent['step_counter']
        if steps < 20 or gold_total < 1000:
            self.intelligent['epsilon'] = 0
        elif steps < 60 or gold_total < 2000:
            self.intelligent['epsilon'] = 49
        else:
            self.intelligent['epsilon'] = 99
        
    def tactic_rest(self):
        gold_total = self.map.gold_total()
        steps = self.intelligent['step_counter']
        on_gold = (not self.need_target() and self.intelligent['same_position'] > 1)
        if steps < 6 or gold_total < 300 or on_gold:
            self.intelligent['rest_counter'] = 3
        elif steps < 20 or gold_total < 1000:
            self.intelligent['rest_counter'] = 2
        else:
            self.intelligent['rest_counter'] = 1

    def need_target(self):
        gold_total = self.map.gold_total()
        steps = self.intelligent['step_counter']
        amount = self.map.gold_amount(self.x, self.y)
        if amount > 0:
            if steps < 60 or gold_total < 2000:
                return False
            elif self.intelligent['same_position'] * 50 <= amount:
                return False
            else:
                return True
        else:
            return True

    def need_corner(self):
        if self.intelligent['corner'] != None:
            window = self.intelligent['window']
            cx, cy = self.intelligent['corner']
            for i in range(window['height']):
                for j in range(window['width']):
                    if self.check_position(cx + j, cy + i):
                        return False
        return True
    
    def find_corner(self):
        self.intelligent['corner'] = None
        window = self.intelligent['window']
        amount_max = 0
        for y in range(self.map.height):
            for x in range(self.map.width):
                amount = self.map.gold_amount_square(x, y, window)
                if amount > amount_max:
                    amount_max = amount
                    self.intelligent['corner'] = [x, y]

    def check_position(self, x, y):
        amount = self.map.gold_amount(x, y)
        if (self.x, self.y) != (x,y) and amount > 0:
            distance = abs(self.x - x) + abs(self.y - y)
            players = 0 if self.intelligent['players'] is None else self.count_player(x, y)
            epsilon = amount - 50 * players * distance
            if epsilon > self.intelligent['epsilon']:
                return True
        return False

    def find_target(self):
        self.tactic_choose()
        self.intelligent['target'] = None
        window = self.intelligent['window']
        cx, cy = self.intelligent['corner']
        distance_min = self.map.width + self.map.height
        epsilon_max = 0
        for i in range(window['height']):
            for j in range(window['width']):
                x, y = cx + j, cy + i
                amount = self.map.gold_amount(x, y)
                if (self.x, self.y) != (x,y) and amount > 0:
                    distance = abs(self.x - x) + abs(self.y - y)
                    players = 0 if self.intelligent['players'] is None else self.count_player(x, y)
                    epsilon = amount - 50 * players * distance
                    if epsilon > self.intelligent['epsilon']:
                        check = (
                            distance < distance_min
                            or (distance == distance_min and epsilon > epsilon_max)
                        )
                        if check:
                            distance_min = distance
                            epsilon_max = epsilon
                            self.intelligent['target'] = [x, y]

    def find_direction(self):
        target_x, target_y = self.intelligent['target']
        current_x, current_y = self.x, self.y
        turnleft = (target_x < current_x)
        turnright = (target_x > current_x)
        turnup = (target_y < current_y)
        turndown = (target_y > current_y)
        noupdown = (not turnup) and (not turndown)
        norightleft = (not turnright) and (not turnleft)
        if noupdown:
            if turnright:
                return self.ACTION_GO_RIGHT
            else:
                return self.ACTION_GO_LEFT
        elif norightleft:
            if turndown:
                return self.ACTION_GO_DOWN
            else:
                return self.ACTION_GO_UP
        else:
            cellup, celldown, cellleft, cellright = self.map.cell_around(self.x, self.y)
            if turnup and turnright:
                if cellup < cellright:
                    return self.ACTION_GO_UP
                else:
                    return self.ACTION_GO_RIGHT
            elif turnup and turnleft:
                if cellup < cellleft:
                    return self.ACTION_GO_UP
                else:
                    return self.ACTION_GO_LEFT
            elif turndown and turnright:
                if celldown < cellright:
                    return self.ACTION_GO_DOWN
                else:
                    return self.ACTION_GO_RIGHT
            elif turndown and turnleft:
                if celldown < cellleft:
                    return self.ACTION_GO_DOWN
                else:
                    return self.ACTION_GO_LEFT

    def check_energy(self, action):
        cellup, celldown, cellleft, cellright = self.map.cell_around(self.x, self.y)
        if action == self.ACTION_CRAFT and 5 < self.energy:
            return self.ACTION_CRAFT
        elif action == self.ACTION_GO_UP and cellup < self.energy:
            return self.ACTION_GO_UP
        elif action == self.ACTION_GO_DOWN and celldown < self.energy:
            return self.ACTION_GO_DOWN
        elif action == self.ACTION_GO_LEFT and cellleft < self.energy:
            return self.ACTION_GO_LEFT
        elif action == self.ACTION_GO_RIGHT and cellright < self.energy:
            return self.ACTION_GO_RIGHT
        else:
            self.tactic_rest()
            return self.ACTION_FREE
    
    def get_action(self):
        try:
            if self.intelligent["rest_counter"] in range(1,3):
                self.intelligent["rest_counter"] += 1
                return self.ACTION_FREE
            else:
                if self.need_target():
                    if self.need_corner():
                        self.tactic_window()
                        self.find_corner()
                    self.find_target()
                    action = self.find_direction()
                else:
                    action = self.ACTION_CRAFT
                return self.check_energy(action)
        except:
            return self.ACTION_FREE

    def print_state(self):
        print('-'*8)
        print('[INFO] last action: {}, score: {:6d}, energy: {:3d}, step: {:3d}, corner: {}, target: {}, miner: {}'.format(
            self.lastAction, self.score, self.energy, self.intelligent['step_counter'], self.intelligent['corner'], self.intelligent['target'], [self.x, self.y]))
        for y in range(self.map.height):
            for x in range(self.map.width):
                if [x, y] == [self.x, self.y]: s = 'M'
                elif [x, y] == self.intelligent['target']: s = 'T'
                elif [x, y] == self.intelligent['corner']: s = 'C'
                else: s = ' '
                print('{:3d}.{}.{}'.format(self.map.gold_amount(x, y), s, self.map.obstacles[y][x]), end='|')
            print()
            
            
def recv_all(sock):
    buff_size = 4096
    recv_data = b""
    while True:
        part = sock.recv(buff_size)
        recv_data += part
        if len(part) < buff_size:
            break
    message = recv_data.decode("utf-8")
    #print("Message from server:", message)
    return message

def str2Json(str):
    return json.loads(str, encoding="utf-8")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    try:
        s.connect((HOST, PORT))
        print("Connected to server.")
        miner = None
        while True:
            try:
                message = recv_all(s)
                data = str2Json(message)
                if "gameinfo" in data:
                    miner = Miner(data)
                    #print(miner)
                    action = str(miner.get_action())
                    #print("Next action:", action)
                    miner.print_state()
                    s.send(action.encode("utf-8"))
                else:
                    miner.update_state(data)
                    #print(miner)
                    action = str(miner.get_action())
                    #print("Next action:", action)
                    miner.print_state()
                    s.send(action.encode("utf-8"))
            except Exception as e:
                import traceback
                traceback.print_exc()
                print("Finished.")
                break
    except Exception as e:
        print("Cannot connect.")